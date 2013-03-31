import boto
import boto.ec2
import os
import time

ami = "ami-1cf5ff68"
region = "eu-west-1"

def create_keypair(path, ec2, key_name='-vpn-key'):
    key_file = os.path.join(path, "%s.pem" % key_name)

    if not os.path.exists(path):
        os.mkdir(path)

    if not os.path.exists(key_file):
        key_pair = ec2.create_key_pair(key_name)
        key_pair.save(path)

        os.chmod(key_file, 600)

    return (key_name, key_file)

def create_machine():
    ec2 = boto.ec2.connect_to_region(region)

    key_name, key_file = create_keypair('.keys', ec2)
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

    n = instance.ip_address
    print "NOTICE* Started instance %s" % n
    f = open('.machine', 'w')
    f.write(n + "\n")
    f.close()


create_machine()
