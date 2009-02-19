#!/usr/bin/python
# L.S. Keijser - Stone-IT
# keijser@stone-it.com
#
# Will check cobbler server for system and generate Nagios config files
#
# Usage: ./cobnag.py -y system_name -k customer_name
# Generated files will then be placed in /etc/nagios/objects/<customer_name>/<system_name>.cfg
#--------------------------------------------------------------------------------------------------------------
import xmlrpclib
from optparse import OptionParser
import re, os, sys 

# Define login credentials for Cobbler here:
cobbler_uri = "http://11.22.33.44/cobbler_api_rw"

# Define profile-related services. Be sure to include the same profile for critical and noncritical!
# Define critical profile-related services here (checkname or proc:<name> or tcp:<port> or procargs:<args>)):
services_profile_critical = { 
    'default': ['ssh','load','procargs:funcd','procargs:puppetd'], 
    'cobbler': ['procargs:cobblerd', 'procargs:puppetmaster'], 
    'firewall': [], 
    'nas': ['procargs:drbd0_worker', 'procargs:drbd0_receiver', 'procargs:drbd0_asender', 'procargs:drbd1_worker', 'procargs:drbd1_receiver', 'procargs:drbd1_asender', 'proc:heartbeat'], 
    'openvpn': ['proc:openvpn'],
    'testvirtual': [],
    'xenhost': ['procargs:xend'], 
    'xenhost-mgmt': ['procargs:xend'] 
}

# Define noncritical profile-related services here (checkname or proc:<name> or tcp:<port> or procargs:<args>):
services_profile_noncritical = { 
    'default': ['ping','users'], 
    'cobbler': [], 
    'firewall': [], 
    'nas': [ 'dell_phydisk', 'dell_power', 'dell_temp', 'dell_virtdisk' ], 
    'openvpn': [],
    'testvirtual': [],
    'xenhost': [ 'dell_phydisk', 'dell_power', 'dell_temp', 'dell_virtdisk' ], 
    'xenhost-mgmt': [ 'dell_phydisk', 'dell_power', 'dell_temp', 'dell_virtdisk' ] 
}

# Define service commands here
checkcommand = {
    "ssh": "check_ssh", 
    "load": "check_nrpe!check_load!15,10,5 30,25,20", 
    "ping": "check_ping!100.0,20%!500.0,60%", 
    "users": "check_nrpe!check_users!5 10", 
    "proc:": "check_nrpe!check_proc!1", 
    "procargs:": "check_nrpe!check_procargs!1", 
    "tcp:": "check_tcp!", 
    "smtp": "check_smtp",
    "http": "check_http",
    "yum": "check_nrpe!check_yum",
    "kernel": "check_nrpe!check_kernel",
    "dell_phydisk": "check_nrpe!check_dell!phydisk",
    "dell_power": "check_nrpe!check_dell!power",
    "dell_temp": "check_nrpe!check_dell!temp",
    "dell_virtdisk": "check_nrpe!check_dell!virtdisk"
}

############################################################################
remote = xmlrpclib.Server(cobbler_uri)

# command line options
parser = OptionParser(usage="%prog -y <system_name> -k <customer_name>",version="%prog 0.0.1")
parser.add_option("-y", "--system", action="store", type="string", dest="system_name", help="Sytem name")
parser.add_option("-k", "--customer", action="store", type="string", dest="customer_name", help="Customer name - One word, no funny business!")

# parse cmd line options
(options, args) = parser.parse_args()

# check for all args
if options.system_name is None or options.customer_name is None:
    parser.error("Incorrect number of arguments!")

# check if customer dir exists, create it if it doesn't
customer_dir = '/etc/nagios/objects/' + str(options.customer_name)

if not os.path.exists(customer_dir):
    print "Customer directory didn't exist, making ..."
    os.mkdir(customer_dir)

my_system = remote.get_system(options.system_name)

print "Now processing system " + options.system_name

try:
    kickstart = remote.generate_kickstart(my_system['profile'], my_system['name'])
except KeyError:
    print "Error, profile or system name not found. Bailing out..."
    sys.exit()

# Write kickstart to file
f=open('/tmp/rend-ks.tmp', 'w')
f.write(kickstart)
f.close()

# Read lines in variable
file=open('/tmp/rend-ks.tmp', 'r')
lines = file.readlines()
file.close()

# Find line numbers for partition info:
p_begin = re.compile('# BEGINPARTITIONS')
p_end = re.compile('# ENDPARTITIONS')
for i, line in enumerate(lines):
    if p_begin.search(line):
        beginpart = i + 1
    if p_end.search(line):
        endpart = i - 1

p_lines = range(beginpart, endpart)

fstype = re.compile('fstype')

partitions = []

for i, line in enumerate(lines):
    if i in p_lines:
        if fstype.search(line):
            partitions.append(line.split(' ')[1])

print "\nGenerating Nagios config file for this system in " + str(customer_dir) + "/" + str(my_system['name']) + ".cfg\n"

f=open(customer_dir + '/' + str(my_system['name']) + '.cfg', 'w')

# Define host once
f.write("define host{\n")
f.write("\tuse\t\tregular-host\n")
f.write("\thost_name\t" + str(my_system['name']) + "\n")
f.write("\talias\t\t" + str(my_system['name']) + "\n")
f.write("\taddress\t\t" + str(my_system['interfaces']['intf0']['ip_address']) + "\n")
f.write("\t}\n\n")

# Define all services
# Profile-related Critical services:
for service in services_profile_critical[str(my_system['profile'])]:
    f.write("define service{\n")
    f.write("\thost_name\t\t" + str(my_system['name']) + "\n")
    serv_proc = re.compile('proc:')
    serv_tcp = re.compile('tcp:')
    serv_procargs = re.compile('procargs:')
    if serv_proc.search(service):
        f.write("\tservice_description\tProcess " + str(service).split(':')[1] + "\n")
        f.write("\tcheck_command\t\t" + checkcommand['proc:'] + ": " + str(service).split(':')[1] + "\n")
    elif serv_tcp.search(service):
        f.write("\tservice_description\tTCP port " + str(service).split(':')[1] + "\n")
        f.write("\tcheck_command\t\t" + checkcommand['tcp:'] +  str(service).split(':')[1] + "\n")
    elif serv_procargs.search(service):
        f.write("\tservice_description\tProcess with argument " + str(service).split(':')[1] + "\n")
        f.write("\tcheck_command\t\t" + checkcommand['procargs:'] + ": " + str(service).split(':')[1] + "\n")
    else:
        f.write("\tservice_description\t" + str(service) + "\n")
        f.write("\tcheck_command\t\t" + checkcommand[str(service)] + "\n")
    f.write("\tuse\t\t\tcritical-service\n")
    f.write("\t}\n\n")

# Profile-related Noncritical services:
for service in services_profile_noncritical[str(my_system['profile'])]:
    f.write("define service{\n")
    f.write("\thost_name\t\t" + str(my_system['name']) + "\n")
    serv_proc = re.compile('proc:')
    serv_tcp = re.compile('tcp:')
    serv_procargs = re.compile('procargs:')
    if serv_proc.search(service):
        f.write("\tservice_description\tProcess " + str(service).split(':')[1] + "\n")
        f.write("\tcheck_command\t\t" + checkcommand['proc:'] + ": " + str(service).split(':')[1] + "\n")
    elif serv_tcp.search(service):
        f.write("\tservice_description\tTCP port " + str(service).split(':')[1] + "\n")
        f.write("\tcheck_command\t\t" + checkcommand['tcp:'] +  str(service).split(':')[1] + "\n")
    elif serv_procargs.search(service):
        f.write("\tservice_description\tProcess with argument " + str(service).split(':')[1] + "\n")
        f.write("\tcheck_command\t\t" + checkcommand['procargs:'] + ": " + str(service).split(':')[1] + "\n")
    else:
        f.write("\tservice_description\t" + str(service) + "\n")
        f.write("\tcheck_command\t\t" + checkcommand[str(service)] + "\n")
    f.write("\tuse\t\t\tnoncritical-service\n")
    f.write("\t}\n\n")

# Standard Critical services:
for service in services_profile_critical['default']:
    f.write("define service{\n")
    f.write("\thost_name\t\t" + str(my_system['name']) + "\n")
    serv_proc = re.compile('proc:')
    serv_tcp = re.compile('tcp:')
    serv_procargs = re.compile('procargs:')
    if serv_proc.search(service):
        f.write("\tservice_description\tProcess " + str(service).split(':')[1] + "\n")
        f.write("\tcheck_command\t\t" + checkcommand['proc:'] + ": " + str(service).split(':')[1] + "\n")
    elif serv_tcp.search(service):
        f.write("\tservice_description\tTCP port " + str(service).split(':')[1] + "\n")
        f.write("\tcheck_command\t\t" + checkcommand['tcp:'] +  str(service).split(':')[1] + "\n")
    elif serv_procargs.search(service):
        f.write("\tservice_description\tProcess with argument " + str(service).split(':')[1] + "\n")
        f.write("\tcheck_command\t\t" + checkcommand['procargs:'] + ": " + str(service).split(':')[1] + "\n")
    else:
        f.write("\tservice_description\t" + str(service) + "\n")
        f.write("\tcheck_command\t\t" + checkcommand[str(service)] + "\n")
    f.write("\tuse\t\t\tcritical-service\n")
    f.write("\t}\n\n")

# Standard Noncritical services:
for service in services_profile_noncritical['default']:
    f.write("define service{\n")
    f.write("\thost_name\t\t" + str(my_system['name']) + "\n")
    serv_proc = re.compile('proc:')
    serv_tcp = re.compile('tcp:')
    serv_procargs = re.compile('procargs:')
    if serv_proc.search(service):
        f.write("\tservice_description\tProcess " + str(service).split(':')[1] + "\n")
        f.write("\tcheck_command\t\t" + checkcommand['proc:'] + ": " + str(service).split(':')[1] + "\n")
    elif serv_tcp.search(service):
        f.write("\tservice_description\tTCP port " + str(service).split(':')[1] + "\n")
        f.write("\tcheck_command\t\t" + checkcommand['tcp:'] +  str(service).split(':')[1] + "\n")
    elif serv_procargs.search(service):
        f.write("\tservice_description\tProcess with argument " + str(service).split(':')[1] + "\n")
        f.write("\tcheck_command\t\t" + checkcommand['procargs:'] + ": " + str(service).split(':')[1] + "\n")
    else:
        f.write("\tservice_description\t" + str(service) + "\n")
        f.write("\tcheck_command\t\t" + checkcommand[str(service)] + "\n")
    f.write("\tuse\t\t\tnoncritical-service\n")
    f.write("\t}\n\n")

# Define all found partitions
for part in partitions:
    f.write("define service{\n")
    f.write("\thost_name\t\t" + str(my_system['name']) + "\n")
    f.write("\tservice_description\tPartition " + str(part) + "\n")
    if part == 'swap':
        f.write("\tcheck_command\t\tcheck_nrpe!check_swap!10% 5%\n")
    else: 
        f.write("\tcheck_command\t\tcheck_nrpe!check_disk!10% 5% " + str(part) + "\n")
    f.write("\tuse\t\t\tcritical-service\n")
    f.write("\t}\n\n")

f.close()

# Generate hostgroup file for all .cfg files found in customer's dir
members=[]
dirList=os.listdir(customer_dir)
hostgroupconfig = re.compile('hostgroup.cfg')

for cfg in dirList:
    if not hostgroupconfig.search(cfg):
        members.append(cfg.replace('.cfg','') + ', ')

f=open(customer_dir + '/hostgroup.cfg', 'w')
f.write("define hostgroup{\n")
f.write("\thostgroup_name\t" + options.customer_name + "\n")
f.write("\talias\t\t" + options.customer_name + "'s Systems\n")
f.write("\tmembers\t\t")
for m in members:
    f.write(m)
f.write("\n")
f.write("\t}\n")

f.close()

