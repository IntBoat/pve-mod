#!/usr/bin/env python3
"""Apply minimal CPU temperature patches to PVE Nodes.pm and pvemanagerlib.js."""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PVE_CPUTEMP_MOD"
NODES = Path("/usr/share/perl5/PVE/API2/Nodes.pm")
JS = Path("/usr/share/pve-manager/js/pvemanagerlib.js")

STATUS_INJECT = f"""
        # {MARKER}: live CPU package temperature (°C)
        eval {{
            my $sensors_json = `sensors -j 2>/dev/null`;
            if ($sensors_json) {{
                require JSON;
                my $sensors = eval {{ JSON::decode_json($sensors_json) }};
                if (ref($sensors) eq 'HASH') {{
                    CHIP: foreach my $chip (keys %$sensors) {{
                        next unless $chip =~ /coretemp|k10temp|zenpower/;
                        my $payload = $sensors->{{$chip}};
                        next unless ref($payload) eq 'HASH';
                        foreach my $prefer ('Package id 0', 'Tctl', 'Tdie') {{
                            my $entry = $payload->{{$prefer}};
                            next unless ref($entry) eq 'HASH';
                            if (defined $entry->{{temp1_input}}) {{
                                $res->{{cputemp}} = 0 + $entry->{{temp1_input}};
                                last CHIP;
                            }}
                            foreach my $k (sort keys %$entry) {{
                                if ($k =~ /_input$/ && defined $entry->{{$k}}) {{
                                    $res->{{cputemp}} = 0 + $entry->{{$k}};
                                    last CHIP;
                                }}
                            }}
                        }}
                        foreach my $label (keys %$payload) {{
                            next unless ref($payload->{{$label}}) eq 'HASH';
                            my $entry = $payload->{{$label}};
                            if (defined $entry->{{temp1_input}}) {{
                                $res->{{cputemp}} = 0 + $entry->{{temp1_input}};
                                last CHIP;
                            }}
                            foreach my $k (sort keys %$entry) {{
                                if ($k =~ /_input$/ && defined $entry->{{$k}}) {{
                                    $res->{{cputemp}} = 0 + $entry->{{$k}};
                                    last CHIP;
                                }}
                            }}
                        }}
                    }}
                }}
            }}
        }};

"""

CPUTEMP_API = f"""
__PACKAGE__->register_method({{
    name => 'cputemprrddata',
    path => 'cputemprrddata',
    method => 'GET',
    protected => 1,
    proxyto => 'node',
    permissions => {{
        check => ['perm', '/nodes/{{node}}', ['Sys.Audit']],
    }},
    description => "Read CPU temperature RRD statistics ({MARKER})",
    parameters => {{
        additionalProperties => 0,
        properties => {{
            node => get_standard_option('pve-node'),
            timeframe => {{
                description => "Specify the time frame you are interested in.",
                type => 'string',
                enum => ['hour', 'day', 'week', 'month', 'year', 'decade'],
            }},
            cf => {{
                description => "The RRD consolidation function",
                type => 'string',
                enum => ['AVERAGE', 'MAX'],
                optional => 1,
            }},
        }},
    }},
    returns => {{
        type => "array",
        items => {{
            type => "object",
            properties => {{}},
        }},
    }},
    code => sub {{
        my ($param) = @_;
        my $nodename = $param->{{node}} // PVE::INotify::nodename();
        return PVE::RRD::create_rrd_data(
            "pve-mod-cputemp/$nodename", $param->{{timeframe}}, $param->{{cf}},
        );
    }},
}});

"""

MODEL_BLOCK = f"""
Ext.define('pve-rrd-cputemp', {{ // {MARKER}
    extend: 'Ext.data.Model',
    fields: [
        'cputemp',
        {{ type: 'date', dateFormat: 'timestamp', name: 'time' }},
    ],
}});
"""

STATUS_WIDGET = f"""
        {{
            // {MARKER}
            itemId: 'cputemp',
            colspan: 2,
            iconCls: 'fa fa-fw fa-thermometer-half',
            title: gettext('CPU Temperature'),
            valueField: 'cputemp',
            warningThreshold: 0.75,
            criticalThreshold: 0.9,
            renderer: function (value) {{
                if (!Ext.isNumeric(value)) {{
                    return 'N/A';
                }}
                return Ext.Number.toFixed(value, 1) + ' °C';
            }},
            calculate: function (used) {{
                if (!Ext.isNumeric(used)) {{
                    return 0;
                }}
                return Math.min(Math.max(used / 100, 0), 1);
            }},
        }},
"""


def patch_nodes(text: str) -> str:
    if MARKER in text:
        return text

    child = "            { name => 'rrddata' },\n"
    child_new = (
        "            { name => 'rrddata' },\n"
        f"            {{ name => 'cputemprrddata' }}, # {MARKER}\n"
    )
    if child not in text:
        raise RuntimeError("Nodes.pm: rrddata child entry not found")
    text = text.replace(child, child_new, 1)

    status_anchor = """        $res->{rootfs} = {
            total => $dinfo->{blocks},
            avail => $dinfo->{bavail},
            used => $dinfo->{used},
            free => $dinfo->{blocks} - $dinfo->{used},
        };

        return $res;
"""
    if status_anchor not in text:
        raise RuntimeError("Nodes.pm: status return anchor not found")
    text = text.replace(
        status_anchor,
        status_anchor.replace("        return $res;\n", STATUS_INJECT + "        return $res;\n"),
        1,
    )

    api_anchor = """__PACKAGE__->register_method({
    name => 'syslog',
    path => 'syslog',
    method => 'GET',
    description => "Read system log",
"""
    if api_anchor not in text:
        raise RuntimeError("Nodes.pm: syslog method anchor not found")
    text = text.replace(api_anchor, CPUTEMP_API + api_anchor, 1)
    return text


def patch_js(text: str) -> str:
    if MARKER in text:
        return text

    model_anchor = "Ext.define('pve-rrd-node', {"
    if model_anchor not in text:
        raise RuntimeError("pvemanagerlib.js: pve-rrd-node model not found")
    text = text.replace(model_anchor, MODEL_BLOCK + model_anchor, 1)

    version_anchor = """        {
            itemId: 'version',
            colspan: 2,
            printBar: false,
            title: gettext('Manager Version'),
            textField: 'pveversion',
            value: '',
        },
    ],

    updateTitle: function () {
        var me = this;
        var uptime = Proxmox.Utils.render_uptime(me.getRecordValue('uptime'));
        me.setTitle(me.pveSelNode.data.node + ' (' + gettext('Uptime') + ': ' + uptime + ')');
    },
"""
    if version_anchor not in text:
        raise RuntimeError("pvemanagerlib.js: StatusView version item not found")
    text = text.replace(
        version_anchor,
        version_anchor.replace(
            "        },\n    ],\n\n    updateTitle:",
            "        },\n" + STATUS_WIDGET + "    ],\n\n    updateTitle:",
            1,
        ),
        1,
    )

    # Bump StatusView height slightly for the extra row
    old_height = "    alias: 'widget.pveNodeStatus',\n\n    height: 350,"
    new_height = f"    alias: 'widget.pveNodeStatus',\n\n    height: 380, // {MARKER}"
    if old_height not in text:
        raise RuntimeError("pvemanagerlib.js: pveNodeStatus height not found")
    text = text.replace(old_height, new_height, 1)

    summary_old = """        var rrdstore = Ext.create('Proxmox.data.RRDStore', {
            rrdurl: '/api2/json/nodes/' + nodename + '/rrddata',
            model: 'pve-rrd-node',
        });

        let nodeStatus = Ext.create('PVE.node.StatusView', {
            xtype: 'pveNodeStatus',
            rstore: rstore,
            width: 770,
            pveSelNode: me.pveSelNode,
        });

        Ext.apply(me, {
            tbar: [version_btn, '->', { xtype: 'proxmoxRRDTypeSelector' }],
            nodeStatus: nodeStatus,
            items: [
                {
                    xtype: 'container',
                    itemId: 'itemcontainer',
                    layout: 'column',
                    minWidth: 700,
                    defaults: {
                        minHeight: 360,
                        padding: 5,
                        columnWidth: 1,
                    },
                    items: [
                        nodeStatus,
                        {
                            xtype: 'proxmoxRRDChart',
                            title: gettext('CPU Usage'),
                            fields: ['cpu', 'iowait'],
                            fieldTitles: [gettext('CPU usage'), gettext('IO delay')],
                            unit: 'percent',
                            store: rrdstore,
                        },
"""
    summary_new = f"""        var rrdstore = Ext.create('Proxmox.data.RRDStore', {{
            rrdurl: '/api2/json/nodes/' + nodename + '/rrddata',
            model: 'pve-rrd-node',
        }});

        // {MARKER}
        var cputempRrdStore = Ext.create('Proxmox.data.RRDStore', {{
            rrdurl: '/api2/json/nodes/' + nodename + '/cputemprrddata',
            model: 'pve-rrd-cputemp',
        }});

        let nodeStatus = Ext.create('PVE.node.StatusView', {{
            xtype: 'pveNodeStatus',
            rstore: rstore,
            width: 770,
            pveSelNode: me.pveSelNode,
        }});

        Ext.apply(me, {{
            tbar: [version_btn, '->', {{ xtype: 'proxmoxRRDTypeSelector' }}],
            nodeStatus: nodeStatus,
            items: [
                {{
                    xtype: 'container',
                    itemId: 'itemcontainer',
                    layout: 'column',
                    minWidth: 700,
                    defaults: {{
                        minHeight: 360,
                        padding: 5,
                        columnWidth: 1,
                    }},
                    items: [
                        nodeStatus,
                        {{
                            xtype: 'proxmoxRRDChart',
                            title: gettext('CPU Usage'),
                            fields: ['cpu', 'iowait'],
                            fieldTitles: [gettext('CPU usage'), gettext('IO delay')],
                            unit: 'percent',
                            store: rrdstore,
                        }},
                        {{
                            // {MARKER}
                            xtype: 'proxmoxRRDChart',
                            title: gettext('CPU Temperature'),
                            fields: [
                                {{
                                    yField: 'cputemp',
                                    title: gettext('CPU Temperature'),
                                    tooltip: {{
                                        trackMouse: true,
                                        renderer: function (toolTip, record, item) {{
                                            let value = record.get('cputemp');
                                            if (value === null || value === undefined) {{
                                                toolTip.setHtml(gettext('No Data'));
                                            }} else {{
                                                let time = new Date(record.get('time'));
                                                toolTip.setHtml(
                                                    gettext('CPU Temperature') +
                                                        ': ' +
                                                        Ext.Number.toFixed(value, 1) +
                                                        ' °C<br>' +
                                                        time,
                                                );
                                            }}
                                        }},
                                    }},
                                }},
                            ],
                            fieldTitles: [gettext('CPU Temperature') + ' (°C)'],
                            store: cputempRrdStore,
                        }},
"""
    if summary_old not in text:
        raise RuntimeError("pvemanagerlib.js: Summary CPU Usage block not found")
    text = text.replace(summary_old, summary_new, 1)

    listeners_old = """            listeners: {
                activate: function () {
                    rstore.setInterval(1000);
                    rstore.startUpdate(); // just to be sure
                    rrdstore.startUpdate();
                },
                destroy: function () {
                    rstore.setInterval(5000); // don't stop it, it's not ours!
                    rrdstore.stopUpdate();
                },
            },
"""
    listeners_new = f"""            listeners: {{
                activate: function () {{
                    rstore.setInterval(1000);
                    rstore.startUpdate(); // just to be sure
                    rrdstore.startUpdate();
                    cputempRrdStore.startUpdate(); // {MARKER}
                }},
                destroy: function () {{
                    rstore.setInterval(5000); // don't stop it, it's not ours!
                    rrdstore.stopUpdate();
                    cputempRrdStore.stopUpdate(); // {MARKER}
                }},
            }},
"""
    if listeners_old not in text:
        raise RuntimeError("pvemanagerlib.js: Summary listeners block not found")
    text = text.replace(listeners_old, listeners_new, 1)
    return text


def main() -> int:
    nodes = NODES.read_text()
    js = JS.read_text()

    if MARKER in nodes and MARKER in js:
        print("Patches already applied.")
        return 0

    new_nodes = patch_nodes(nodes)
    new_js = patch_js(js)

    NODES.write_text(new_nodes)
    JS.write_text(new_js)
    print("Patched Nodes.pm and pvemanagerlib.js")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
