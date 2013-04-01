import boto
import boto.ec2
import os
import time
import paramiko

ami = "ami-1cf5ff68"
region = "eu-west-1"

def create_machine():
    ec2 = boto.ec2.connect_to_region(region)

    key_name = 'vpn-key'
    image = ec2.get_image(ami)

    reservation = image.run(1,1,key_name, 
                            instance_type='t1.micro',
                            security_groups=['vpn'])

    itrs = 0
    found = False
    instance = reservation.instances[0]
    while not found and itrs < 10:
        instance.update()
        time.sleep(5)

        if instance.state == 'running':
            found = True

        itrs += 1

    if not found:
        print "ERROR* Could not start instance"
        exit(1)

    n = instance.public_dns_name
    print "NOTICE* Started instance %s" % n
    f = open('.machine', 'w')
    f.write(n + "\n")
    f.close()

def provision(ip):
    keypath = ".keys/vpn-key.pem"
    client = paramiko.SSHClient()
    print "NOTICE* Trying to connect to %s" % ip

    k = paramiko.RSAKey.from_private_key_file(keypath)
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(ip, username='ubuntu', pkey=k)

    install_vpn_apt(client)
    install_network_br0(client)
    install_gen_cert_auth(client)
    install_config(client)

def install_network_br0(client):
    networking_file = '/etc/network/interfaces'
    sftp = client.open_sftp()
    network_file = sftp.open(networking_file).read()

    if "br0" not in network_file:
        print "---- INSTALLING network interface files ----"
        lines = """
iface br0 inet static 
  address 192.168.1.10 
  netmask 255.255.255.0
  gateway 192.168.1.1
  bridge_ports eth0
  bridge_fd 9      ## from the libvirt docs (forward delay time)
  bridge_hello 2   ## from the libvirt docs (hello time)
  bridge_maxage 12 ## from the libvirt docs (maximum message age)
  bridge_stp off   ## from the libvirt docs (spanning tree protocol)
"""
        content = network_file + lines
        
        network_file = sftp.open('/tmp/ifaces','w')
        network_file.write(content)
        network_file.close()
        network_file = sftp.open(networking_file).read()
        run(client, 'sudo mv /tmp/ifaces %s' % networking_file)
        run(client, 'sudo /etc/init.d/networking restart')

def install_config(client):
    sftp = client.open_sftp()
    try:
        sftp.stat('/etc/openvpn/up.sh')
        return # We've already created it
    except IOError, e:
        upsh = sftp.open('/tmp/up.sh','w')
        upsh.write("""#!/bin/sh

BR=$1
DEV=$2
MTU=$3
/sbin/ip link set "$DEV" up promisc on mtu "$MTU"
/sbin/brctl addif $BR $DEV
""")
        upsh.close()
        run(client, 'sudo mv /tmp/up.sh /etc/openvpn/up.sh')
        run(client, 'sudo chmod +x /etc/openvpn/up.sh')

    try:
        sftp.stat('/etc/openvpn/down.sh')
        return # We've already created it
    except IOError, e:
        upsh = sftp.open('/tmp/down.sh','w')
        upsh.write("""#!/bin/sh

BR=$1
DEV=$2

/sbin/brctl delif $BR $DEV
/sbin/ip link set "$DEV" down
""")
        upsh.close()
        run(client, 'sudo mv /tmp/down.sh /etc/openvpn/down.sh')
        run(client, 'sudo chmod +x /etc/openvpn/down.sh')

def install_gen_cert_auth(client):
    sftp = client.open_sftp()
    try:
        sftp.stat('/etc/openvpn/server.crt')
        return # We've already created it
    except IOError, e:
        run(client, 'sudo rm -rf /etc/openvpn/easy-rsa/') 
        run(client, 'sudo mkdir /etc/openvpn/easy-rsa/') 
        run(client, 'sudo cp -R /usr/share/doc/openvpn/examples/easy-rsa/2.0/* /etc/openvpn/easy-rsa/') 
        
        vars_base = sftp.open('/etc/openvpn/easy-rsa/vars','r').read()
        vars_base += """
export KEY_COUNTRY="US"
export KEY_PROVINCE="CA"
export KEY_CITY="SanFrancisco"
export KEY_ORG="Fort-Funston"
export KEY_EMAIL="me@myhost.mydomain"
"""

        new_vars_file = sftp.open('/tmp/vars', 'w')
        new_vars_file.write(vars_base)
        new_vars_file.close()

        run(client, 'sudo cp /tmp/vars /etc/openvpn/easy-rsa/vars')

        run(client, 'sudo chown -R root:admin /etc/openvpn/easy-rsa/')
        run(client, 'sudo chmod g+w /etc/openvpn/easy-rsa/')
        run(client, """
cd /etc/openvpn/easy-rsa/ && 
sudo ln -s openssl-1.0.0.cnf openssl.cnf &&
source ./vars && ## execute your new vars file
./clean-all && ## Setup the easy-rsa directory (Deletes all keys)
./build-dh  && ## takes a while consider backgrounding
./pkitool --initca && ## creates ca cert and key
./pkitool --server server && ## creates a server cert and key
cd keys &&
openvpn --genkey --secret ta.key &&  ## Build a TLS key
sudo cp server.crt server.key ca.crt dh1024.pem ta.key ../../
""")

        
# ## If you get this error: 
# ##    "The correct version should have a comment that says: easy-rsa version 2.x"
# ## Try This:
# ##     sudo ln -s openssl-1.0.0.cnf openssl.cnf
# ## Refer to: https://bugs.launchpad.net/ubuntu/+source/openvpn/+bug/998918

def install_vpn_apt(client):
    run(client, 'sudo apt-get install -y openvpn bridge-utils')    


def run(client, cmd):
    print "# %s" % cmd
    stdin, stdout, stderr = client.exec_command(cmd)
    line = stdout.readline()
    
    while line:
        print "> %s" % line.strip()
        line = stdout.readline()

#create_machine()
provision(open('.machine','r').read().strip())
