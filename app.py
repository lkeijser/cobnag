"""
cobnag = cobbler-nagios generator (for lack of a better name)

Will check cobbler server for system and generate Nagios config files

Generated files will then be placed in:

/etc/nagios/objects/customers/<customer_name>/<system_name>.cfg

Also, a hostgroup file will be created in the same directory containing 
all the systems.

Copyright 2009 Stone-IT
Leon Keijser <keijser@stone-it.com>

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.
 
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
 
You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
02110-1301  USA
"""

import xmlrpclib
from optparse import OptionParser
import re, os, sys 
from configobj import ConfigObj

def main():

    cobnag_ver = '1.0'

    # command line options
    parser = OptionParser(usage="%prog -y <system_name> -k <customer_name>",version="%prog " + cobnag_ver)
    parser.add_option("-y", "--system", 
            action="store", 
            type="string", 
            dest="system_name", 
            help="Sytem name")
    parser.add_option("-k", "--customer", 
            action="store", 
            type="string", 
            dest="customer_name", 
            help="Customer name - One word, no funny business!")

    # parse cmd line options
    (options, args) = parser.parse_args()

    c = CobNag()
    c.system_name       = options.system_name
    c.customer_name     = options.customer_name

    # check for all args
    if options.system_name is None or options.customer_name is None:
        parser.error("Incorrect number of arguments!")
    else:
        c.run()

class CobNag:

    def __init__(self):
        """
        Constructor. Arguments will be filled in by optparse..
        """
        self.system_name    = None
        self.customer_name  = None


    def run(self):
        """
        CobNag's main function
        """

        # Retrieve settings
        config = ConfigObj('/etc/cobnag.conf')
        section=config['global']
        cobbler_uri=section['cobbler_uri']

        section=config['critical-services']
        services_profile_critical = {}
        for profile, services in section.iteritems():
            if isinstance(services, str):
                cList = []
                cList.append(services)
                services_profile_critical[profile] = cList
            else:
                services_profile_critical[profile] = services

        section=config['noncritical-services']
        services_profile_noncritical = {}
        for profile, services in section.iteritems():
            if isinstance(services, str):
                ncList = []
                ncList.append(services)
                services_profile_noncritical[profile] = ncList
            else:
                services_profile_noncritical[profile] = services

        section=config['commands']
        checkcommand = {}
        for cmd, nagcmd in section.iteritems():
            checkcommand[cmd] = nagcmd

        # Establish server connection
        remote = xmlrpclib.Server(cobbler_uri)

        # check if customer dir exists, create it if it doesn't
        customer_dir = '/etc/nagios/objects/customers/' + str(self.customer_name)

        if not os.path.exists(customer_dir):
            print "Customer directory didn't exist, making ..."
            os.mkdir(customer_dir)

        my_system = remote.get_system(self.system_name)

        print "Now processing system " + self.system_name

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
        f.write("\taddress\t\t" + str(my_system['interfaces']['eth0']['ip_address']) + "\n")
        f.write("\t}\n\n")

        # Define all services
        try:
            # Profile-related Critical services:
            for service in services_profile_critical[my_system['profile']]:
                if not service is '':
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
                if not service is '':
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
        except KeyError:
            print "Error: you didn't specify profile %s in cobnag" % my_system['profile']

        # Standard Critical services:
        for service in services_profile_critical['default']:
            f.write("define service{\n")
            f.write("\thost_name\t\t" + str(my_system['name']) + "\n")
            serv_proc = re.compile('proc:')
            serv_tcp = re.compile('tcp:')
            serv_procargs = re.compile('procargs:')
            if serv_proc.search(service):
                f.write("\tservice_description\tProcess " + str(service).split(':')[1] + "\n")
                f.write("\tcheck_command\t\t" + checkcommand['proc'] + ": " + str(service).split(':')[1] + "\n")
            elif serv_tcp.search(service):
                f.write("\tservice_description\tTCP port " + str(service).split(':')[1] + "\n")
                f.write("\tcheck_command\t\t" + checkcommand['tcp'] +  str(service).split(':')[1] + "\n")
            elif serv_procargs.search(service):
                f.write("\tservice_description\tProcess with argument " + str(service).split(':')[1] + "\n")
                f.write("\tcheck_command\t\t" + checkcommand['procargs'] + ": " + str(service).split(':')[1] + "\n")
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
                f.write("\tcheck_command\t\t" + checkcommand['proc'] + ": " + str(service).split(':')[1] + "\n")
            elif serv_tcp.search(service):
                f.write("\tservice_description\tTCP port " + str(service).split(':')[1] + "\n")
                f.write("\tcheck_command\t\t" + checkcommand['tcp'] +  str(service).split(':')[1] + "\n")
            elif serv_procargs.search(service):
                f.write("\tservice_description\tProcess with argument " + str(service).split(':')[1] + "\n")
                f.write("\tcheck_command\t\t" + checkcommand['procargs'] + ": " + str(service).split(':')[1] + "\n")
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

        print "Generating hostgroup.cfg for all systems for customer %s in %s/hostgroup.cfg" % (self.customer_name, customer_dir)
        f=open(customer_dir + '/hostgroup.cfg', 'w')
        f.write("define hostgroup{\n")
        f.write("\thostgroup_name\t" + self.customer_name + "\n")
        f.write("\talias\t\t" + self.customer_name + "'s Systems\n")
        f.write("\tmembers\t\t")
        for m in members:
            f.write(m)
        f.write("\n")
        f.write("\t}\n")

        f.close()

