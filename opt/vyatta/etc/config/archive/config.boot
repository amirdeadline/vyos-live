interfaces {
    ethernet eth0 {
        address dhcp
        hw-id 00:0c:29:32:2f:3e
        offload {
            gro
            gso
            sg
            tso
        }
    }
    ethernet eth1 {
        hw-id 00:0c:29:32:2f:48
    }
    ethernet eth2 {
        hw-id 00:0c:29:32:2f:52
    }
    ethernet eth3 {
        hw-id 00:0c:29:32:2f:5c
    }
    ethernet eth4 {
        hw-id 00:0c:29:32:2f:66
    }
    ethernet eth5 {
        hw-id 00:0c:29:32:2f:70
    }
    loopback lo {
    }
}
service {
    lldp {
        interface all {
        }
    }
    ntp {
        allow-client {
            address 0.0.0.0/0
            address ::/0
        }
        server time1.deltasase.com {
        }
        server time2.deltasase.com {
        }
        server time3.deltasase.com {
        }
    }
    ssh {
    }
}
system {
    config-management {
        commit-archive {
            location ftp://delta:delta@192.168.172.2/
        }
        commit-revisions 100
    }
    conntrack {
        modules {
            ftp
            h323
            nfs
            pptp
            sip
            sqlnet
            tftp
        }
    }
    console {
        device ttyS0 {
            speed 115200
        }
    }
    host-name delta
    login {
        user amir {
            authentication {
                public-keys amirr@PC01 {
                    key AAAAB3NzaC1yc2EAAAADAQABAAACAQDA+oPyRXaPkOhoeRfiFbLfq2VQa9COG40H2/LgN9S/zgSQARBIVSmVSEnzUeADMkxhiM4B/hcMcwv8pWQh62g22mnHWjGH+Rysvq5SHKPDNsBRHvdsVsc0iqiXzOoPJVVfl1jGPBrU7n2/a0clOx4vt7wg7dmPsB2TH2knia8icutYU1/s+2tDh6fJptluR9hGiusQTz1mnr1yrFEzMWg/aDrZpPSxpFX2rP8wkKw7y8/vKLiCNfrljdZFoliEMUTtalhleRQzFBwRnv8b5sMrmNbvkIv9xdVx1l6++v6leWplDoMj0v39BbLzZpNwwKFuldXszyPOaQDOMPO6y5Hxi/90uObDziuUMyyeTGmjveCIQFVeAf9awzQzJ4ynoEH0YecppFrW6znAw0tWoDA/QC8jY+Hq4xPe8wZabZX3Jw/g/l9n0aaZDVOg/P0pHBOhR2mLByax0Vl5ZkVc/+XMgeZrQJd3yfN/PVeD1ZZ2NVFds1xeWbofF0zGTXQBMC/e9XrajRTI2KZdQhuWeAdRs8HPxAi2aA9N+SZvMQ9NqyDNzKsdIL34OmkLFd60dhx5r6BCGmulCW4YFwWH9z1RhaCe4BLQle5kUuGIAR6/ktgYWuZWeHDPrEWaRbTOKpEw/kHWpW7/emEHmDNh7WM1OXDxD5m4u2C0NHE4ex8aHw==
                    type ssh-rsa
                }
            }
        }
        user delta {
            authentication {
                encrypted-password $6$Abg8SEYokl5DSUNs$lu1QcrZKMKyPHrtW9HRZefT9PTLuEytplrPFvQKC5it9SJS.wQeoXcdR0Hx39NW8p6v9HofP9DhvgCNqPfpoV0
            }
        }
        user vyos {
            authentication {
                encrypted-password $6$QxPS.uk6mfo$9QBSo8u1FkH16gMyAVhus6fU3LOzvLR9Z9.82m3tiHFAxTtIkhaZSWssSgzt4v4dGAL8rhVQxTg0oAG9/q11h/
                plaintext-password ""
            }
        }
    }
    name-server 8.8.8.8
    name-server 4.2.2.4
    name-server eth0
    syslog {
        global {
            facility all {
                level info
            }
            facility protocols {
                level debug
            }
        }
    }
}


// Warning: Do not remove the following line.
// vyos-config-version: "bgp@4:broadcast-relay@1:cluster@1:config-management@1:conntrack@3:conntrack-sync@2:container@1:dhcp-relay@2:dhcp-server@6:dhcpv6-server@1:dns-forwarding@4:firewall@9:flow-accounting@1:https@4:ids@1:interfaces@28:ipoe-server@1:ipsec@12:isis@3:l2tp@4:lldp@1:mdns@1:monitoring@1:nat@5:nat66@1:ntp@2:openconnect@2:ospf@2:policy@5:pppoe-server@6:pptp@2:qos@2:quagga@11:rip@1:rpki@1:salt@1:snmp@3:ssh@2:sstp@4:system@25:vrf@3:vrrp@3:vyos-accel-ppp@2:wanloadbalance@3:webproxy@2"
// Release version: 2.1
