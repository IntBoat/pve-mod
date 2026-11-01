Ext.define('pve-rrd-node', {
    extend: 'Ext.data.Model',
    fields: ['cpu'],
});

Ext.define('PVE.node.StatusView', {
    alias: 'widget.pveNodeStatus',

    height: 350,

    items: [
        {
            colspan: 2,
            title: gettext('Kernel Version'),
            printBar: false,
            textField: 'kversion',
            value: '',
        },
        {
            colspan: 2,
            title: gettext('Boot Mode'),
            printBar: false,
            textField: 'boot-info',
            renderer: (boot) => {
                if (boot.mode === 'legacy-bios') {
                    return 'Legacy BIOS';
                } else if (boot.mode === 'efi') {
                    return `EFI${boot.secureboot ? ' (Secure Boot)' : ''}`;
                }
                return Proxmox.Utils.unknownText;
            },
            value: '',
        },
        {
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
});

function summaryInit() {
        var rrdstore = Ext.create('Proxmox.data.RRDStore', {
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
                        {
                            xtype: 'proxmoxRRDChart',
                            title: gettext('Memory Usage'),
                            store: rrdstore,
                        },
                    ],
                },
            ],
            listeners: {
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
        });
}
