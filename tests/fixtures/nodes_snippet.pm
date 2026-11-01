# Minimal Nodes.pm anchors used by pve-mod patch scripts.

        $res->{rootfs} = {
            total => $dinfo->{blocks},
            avail => $dinfo->{bavail},
            used => $dinfo->{used},
            free => $dinfo->{blocks} - $dinfo->{used},
        };

        return $res;
    },
});

__PACKAGE__->register_method({
    name => 'netstat',
    path => 'netstat',
    method => 'GET',
});

__PACKAGE__->register_method({
    name => 'syslog',
    path => 'syslog',
    method => 'GET',
    description => "Read system log",
});

            { name => 'rrddata' },
            { name => 'other' },
