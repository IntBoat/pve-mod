#!/usr/bin/env python3
"""Apply fan speed patches on top of (or alongside) CPU temperature mods."""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "PVE_FANSPEED_MOD"
NODES = Path("/usr/share/perl5/PVE/API2/Nodes.pm")
JS = Path("/usr/share/pve-manager/js/pvemanagerlib.js")

STATUS_INJECT = f"""
        # {MARKER}: live fan speed (RPM, max of available fans)
        eval {{
            my $fan_rpm;
            my $sensors_json = `sensors -j 2>/dev/null`;
            if ($sensors_json) {{
                require JSON;
                my $sensors = eval {{ JSON::decode_json($sensors_json) }};
                if (ref($sensors) eq 'HASH') {{
                    foreach my $chip (keys %$sensors) {{
                        my $payload = $sensors->{{$chip}};
                        next unless ref($payload) eq 'HASH';
                        foreach my $label (keys %$payload) {{
                            next unless ref($payload->{{$label}}) eq 'HASH';
                            my $entry = $payload->{{$label}};
                            foreach my $k (keys %$entry) {{
                                next unless $k =~ /^fan\\d+_input$/ && defined $entry->{{$k}};
                                my $v = 0 + $entry->{{$k}};
                                next unless $v > 0;
                                $fan_rpm = $v if !defined($fan_rpm) || $v > $fan_rpm;
                            }}
                        }}
                    }}
                }}
            }}
            if (!defined($fan_rpm)) {{
                foreach my $path (glob('/sys/class/hwmon/hwmon*/fan*_input')) {{
                    if (open my $fh, '<', $path) {{
                        my $line = <$fh>;
                        close $fh;
                        if (defined $line && $line =~ /^\\s*([0-9.]+)/) {{
                            my $v = 0 + $1;
                            next unless $v > 0;
                            $fan_rpm = $v if !defined($fan_rpm) || $v > $fan_rpm;
                        }}
                    }}
                }}
            }}
            $res->{{fanspeed}} = $fan_rpm if defined $fan_rpm;
        }};

"""

FAN_API = f"""
__PACKAGE__->register_method({{
    name => 'fanspeedrrddata',
    path => 'fanspeedrrddata',
    method => 'GET',
    protected => 1,
    proxyto => 'node',
    permissions => {{
        check => ['perm', '/nodes/{{node}}', ['Sys.Audit']],
    }},
    description => "Read fan speed RRD statistics ({MARKER})",
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
            "pve-mod-fanspeed/$nodename", $param->{{timeframe}}, $param->{{cf}},
        );
    }},
}});

"""

MODEL_BLOCK = f"""
Ext.define('pve-rrd-fanspeed', {{ // {MARKER}
    extend: 'Ext.data.Model',
    fields: [
        'fanspeed',
        {{ type: 'date', dateFormat: 'timestamp', name: 'time' }},
    ],
}});
"""

STATUS_WIDGET = f"""
        {{
            // {MARKER}
            itemId: 'fanspeed',
            colspan: 2,
            iconCls: 'fa fa-fw fa-tachometer',
            title: gettext('Fan Speed'),
            valueField: 'fanspeed',
            warningThreshold: 0.85,
            criticalThreshold: 0.95,
            renderer: function (value) {{
                if (!Ext.isNumeric(value)) {{
                    return 'N/A';
                }}
                return Ext.Number.toFixed(value, 0) + ' RPM';
            }},
            calculate: function (used) {{
                if (!Ext.isNumeric(used)) {{
                    return 0;
                }}
                // Scale bar to 8000 RPM (typical desktop/mini-PC ceiling)
                return Math.min(Math.max(used / 8000, 0), 1);
            }},
        }},
"""


def patch_nodes(text: str) -> str:
    if MARKER in text:
        return text

    # Register child next to cputemprrddata if present, else rrddata
    if "{ name => 'cputemprrddata' }" in text:
        old = "            { name => 'cputemprrddata' }, # PVE_CPUTEMP_MOD\n"
        new = (
            "            { name => 'cputemprrddata' }, # PVE_CPUTEMP_MOD\n"
            f"            {{ name => 'fanspeedrrddata' }}, # {MARKER}\n"
        )
        if old not in text:
            # tolerate unmarked variant
            old = "            { name => 'cputemprrddata' },\n"
            new = (
                "            { name => 'cputemprrddata' },\n"
                f"            {{ name => 'fanspeedrrddata' }}, # {MARKER}\n"
            )
        if old not in text:
            raise RuntimeError("Nodes.pm: cputemprrddata child entry not found")
        text = text.replace(old, new, 1)
    else:
        old = "            { name => 'rrddata' },\n"
        new = (
            "            { name => 'rrddata' },\n"
            f"            {{ name => 'fanspeedrrddata' }}, # {MARKER}\n"
        )
        if old not in text:
            raise RuntimeError("Nodes.pm: rrddata child entry not found")
        text = text.replace(old, new, 1)

    # Inject status fanspeed just before return $res in status()
    marker_return = "        return $res;\n    },\n});\n\n__PACKAGE__->register_method({\n    name => 'netstat',"
    if marker_return not in text:
        raise RuntimeError("Nodes.pm: status return/netstat anchor not found")
    if STATUS_INJECT.strip() not in text:
        text = text.replace(
            marker_return,
            STATUS_INJECT + marker_return,
            1,
        )

    # API endpoint before syslog (or before cputemprrddata's following syslog)
    api_anchor = """__PACKAGE__->register_method({
    name => 'syslog',
    path => 'syslog',
    method => 'GET',
    description => "Read system log",
"""
    if api_anchor not in text:
        raise RuntimeError("Nodes.pm: syslog method anchor not found")
    text = text.replace(api_anchor, FAN_API + api_anchor, 1)
    return text


def patch_js(text: str) -> str:
    if MARKER in text:
        return text

    # Model after cputemp model if present, else before pve-rrd-node
    if "Ext.define('pve-rrd-cputemp'" in text:
        anchor = "Ext.define('pve-rrd-cputemp', { // PVE_CPUTEMP_MOD"
        # insert after the whole cputemp model block - easier: before pve-rrd-node
        pass
    model_anchor = "Ext.define('pve-rrd-node', {"
    if model_anchor not in text:
        raise RuntimeError("pvemanagerlib.js: pve-rrd-node model not found")
    # If cputemp model exists before node, insert fan model right before pve-rrd-node
    text = text.replace(model_anchor, MODEL_BLOCK + model_anchor, 1)

    # Status widget after cputemp widget if present
    if "itemId: 'cputemp'" in text and "PVE_CPUTEMP_MOD" in text:
        # Insert after the cputemp widget closing
        cputemp_end = """            calculate: function (used) {
                if (!Ext.isNumeric(used)) {
                    return 0;
                }
                return Math.min(Math.max(used / 100, 0), 1);
            },
        },
"""
        if cputemp_end not in text:
            raise RuntimeError("pvemanagerlib.js: cputemp widget end not found")
        text = text.replace(cputemp_end, cputemp_end + STATUS_WIDGET, 1)
    else:
        version_anchor = """            textField: 'pveversion',
            value: '',
        },
    ],

    updateTitle: function () {
"""
        if version_anchor not in text:
            raise RuntimeError("pvemanagerlib.js: version item not found for fan widget")
        text = text.replace(
            version_anchor,
            "            textField: 'pveversion',\n"
            "            value: '',\n"
            "        },\n"
            + STATUS_WIDGET
            + "    ],\n\n    updateTitle: function () {\n",
            1,
        )

    # Keep height for CPU temp + fan (Boot Mode / Manager Version already removed)
    if "height: 360, // PVE_CPUTEMP_MOD" in text and MARKER not in text[
        text.find("height: 360, // PVE_CPUTEMP_MOD") : text.find("height: 360, // PVE_CPUTEMP_MOD") + 80
    ]:
        text = text.replace(
            "height: 360, // PVE_CPUTEMP_MOD",
            f"height: 360, // PVE_CPUTEMP_MOD {MARKER}",
            1,
        )
    elif "height: 380, // PVE_CPUTEMP_MOD" in text:
        text = text.replace(
            "height: 380, // PVE_CPUTEMP_MOD",
            f"height: 360, // PVE_CPUTEMP_MOD {MARKER}",
            1,
        )
    elif "height: 410, // PVE_CPUTEMP_MOD" in text:
        text = text.replace(
            "height: 410, // PVE_CPUTEMP_MOD",
            f"height: 360, // PVE_CPUTEMP_MOD {MARKER}",
            1,
        )

    # Store + chart after CPU Temperature chart if present
    if "cputempRrdStore" in text:
        store_anchor = """        var cputempRrdStore = Ext.create('Proxmox.data.RRDStore', {
            rrdurl: '/api2/json/nodes/' + nodename + '/cputemprrddata',
            model: 'pve-rrd-cputemp',
        });
"""
        store_new = store_anchor + f"""
        // {MARKER}
        var fanspeedRrdStore = Ext.create('Proxmox.data.RRDStore', {{
            rrdurl: '/api2/json/nodes/' + nodename + '/fanspeedrrddata',
            model: 'pve-rrd-fanspeed',
        }});
"""
        if store_anchor not in text:
            raise RuntimeError("pvemanagerlib.js: cputempRrdStore block not found")
        text = text.replace(store_anchor, store_new, 1)

        chart_anchor = """                            fieldTitles: [gettext('CPU Temperature') + ' (°C)'],
                            store: cputempRrdStore,
                        },
"""
        chart_new = (
            chart_anchor
            + f"""                        {{
                            // {MARKER}
                            xtype: 'proxmoxRRDChart',
                            title: gettext('Fan Speed'),
                            fields: [
                                {{
                                    yField: 'fanspeed',
                                    title: gettext('Fan Speed'),
                                    tooltip: {{
                                        trackMouse: true,
                                        renderer: function (toolTip, record, item) {{
                                            let value = record.get('fanspeed');
                                            if (value === null || value === undefined) {{
                                                toolTip.setHtml(gettext('No Data'));
                                            }} else {{
                                                let time = new Date(record.get('time'));
                                                toolTip.setHtml(
                                                    gettext('Fan Speed') +
                                                        ': ' +
                                                        Ext.Number.toFixed(value, 0) +
                                                        ' RPM<br>' +
                                                        time,
                                                );
                                            }}
                                        }},
                                    }},
                                }},
                            ],
                            fieldTitles: [gettext('Fan Speed') + ' (RPM)'],
                            store: fanspeedRrdStore,
                        }},
"""
        )
        if chart_anchor not in text:
            raise RuntimeError("pvemanagerlib.js: CPU Temperature chart end not found")
        text = text.replace(chart_anchor, chart_new, 1)

        listeners_old = """                    cputempRrdStore.startUpdate(); // PVE_CPUTEMP_MOD
                },
                destroy: function () {
                    rstore.setInterval(5000); // don't stop it, it's not ours!
                    rrdstore.stopUpdate();
                    cputempRrdStore.stopUpdate(); // PVE_CPUTEMP_MOD
                },
"""
        listeners_new = f"""                    cputempRrdStore.startUpdate(); // PVE_CPUTEMP_MOD
                    fanspeedRrdStore.startUpdate(); // {MARKER}
                }},
                destroy: function () {{
                    rstore.setInterval(5000); // don't stop it, it's not ours!
                    rrdstore.stopUpdate();
                    cputempRrdStore.stopUpdate(); // PVE_CPUTEMP_MOD
                    fanspeedRrdStore.stopUpdate(); // {MARKER}
                }},
"""
        if listeners_old not in text:
            raise RuntimeError("pvemanagerlib.js: cputemp listeners not found")
        text = text.replace(listeners_old, listeners_new, 1)
    else:
        raise RuntimeError(
            "pvemanagerlib.js: CPU temperature mod not found; install cputemp first"
        )

    return text


def main() -> int:
    nodes = NODES.read_text()
    js = JS.read_text()

    if MARKER in nodes and MARKER in js:
        print("Fan patches already applied.")
        return 0

    NODES.write_text(patch_nodes(nodes))
    JS.write_text(patch_js(js))
    print("Patched Nodes.pm and pvemanagerlib.js for fan speed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
