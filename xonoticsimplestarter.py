#!/usr/bin/env python2

# XonoticSimpleStarter
# Copyright (C) <2016>  <Sebastian Schmidt>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from kivy.app import App
from kivy.support import install_twisted_reactor
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup

install_twisted_reactor()

from xml.etree import cElementTree as ElementTree
from twisted.web.client import getPage

import subprocess
import os
import sys
from collections import OrderedDict


def script_dir():
    return os.path.dirname(os.path.realpath(sys.argv[0]))


class MainGUI(BoxLayout):
    pass


class AddFavouritePopup(Popup):
    pass


class StarterWidget(BoxLayout):
    masterserver = "dpmaster.deathmask.net"
    options = "/?game=xonotic&?&xml=1&?&showplayers=1"
    request_url = "http://" + masterserver + options
    serverstring = "{name} - {gametype}({mod}) - {numplayers}/{maxplayers}"

    def __init__(self, *args, **kwargs):
        self.servers = {}
        self.fav_servers = {}
        self.request_info()
        return super(StarterWidget, self).__init__(*args, **kwargs)

    def add_favourite(self, name, address):
        if not (name and address):
            print "Input is wrong"
            return False
        if not ":" in address:
            print "Please specify the server by ip:port or domain:port"
            return False
        app = App.get_running_app()
        if not app.config.has_section('Favourites'):
            app.config.add_section('Favourites')
        app.config.set('Favourites', name, address)
        app.config.write()
        return True

    def add_favourite_popup(self):
        self.popup = AddFavouritePopup()
        self.popup.ids.add_fav_btn.bind(on_press=self.add_fav_btn_callback)
        self.popup.open()

    def add_fav_btn_callback(self, sender):
        name = self.popup.ids.txt_inpt_name.text.strip()
        address = self.popup.ids.txt_inpt_address.text.strip()
        if self.add_favourite(name, address):
            self.popup.dismiss()
            addr, port = address.split(":")
            self.request_serverinfo(addr, port)

    def connect_to_server(self):
        """
        Get the selected server and connect to it
        """
        if self.ids.server_list.adapter.selection:
            index = self.ids.server_list.adapter.selection[0].index
            server = self.ids.server_list.adapter.sorted_keys[index]
            App.get_running_app().start_xon(server)

    def request_info(self):
        """
        Request the serverlist and info about favourite servers
        from the masterserver.
        """
        self.request_serverlist()
        # Favourites
        config = App.get_running_app().config
        if config.has_section('Favourites'):
            for name in config.options('Favourites'):
                addr_port = config.get('Favourites', name)
                address, port = addr_port.split(":")
                self.request_serverinfo(address, port)
                self.fav_servers[addr_port] = {'name': name,
                                               'status': 'DOWN',
                                               'numplayers': 0,
                                               'maxplayers': 0,
                                               'gametype': "",
                                               'mod': "",
                                               'version': ""}

    def request_serverlist(self):
        """
        Request a list of currently public servers from dpmaster.deathmask.net
        """
        getPage(self.request_url, timeout=5).addCallback(
            self.on_serverlist_retrieved)

    def request_serverinfo(self, address, port):
        """
        Request info about a specific server from dpmaster.deathmask.net
        """
        url = self.request_url + "&server={}:{}".format(address, port)
        getPage(url, timeout=5).addCallback(self.on_serverinfo_retrieved)

    def on_serverlist_retrieved(self, xmlstring):
        """
        Process the serverlist from dpmaster.deathmask.net
        """
        tree = ElementTree.ElementTree(ElementTree.fromstring(xmlstring))
        root = tree.getroot()

        self.servers = OrderedDict()
        # iterate
        for server in root:
            address, serverdict = self.dictify_server(server)
            if serverdict['type'] == 'MASTERSERVER':
                print "Number of servers: ", serverdict['numservers']
            else:
                self.servers[address] = serverdict
        # sort the list
        self.sort_by(self.ids.spinner_sort.text)

    def on_serverinfo_retrieved(self, xmlstring):
        """
        Process the info of a favourite server
        """
        tree = ElementTree.ElementTree(ElementTree.fromstring(xmlstring))
        root = tree.getroot()
        server = root[0]
        address, serverdict = self.dictify_server(server)
        if serverdict['status'] == 'UP':
            self.fav_servers[address] = serverdict
            self.sort_favourites()
        self.update_serverlist()

    def dictify_server(self, server):
        """
        Turn the xml Element 'server' into a dictionary
        """
        serverdict = {}
        if server.attrib['address'] == self.masterserver:
            serverdict['type'] = 'MASTERSERVER'
            serverdict['numservers'] = server.attrib['servers']
        else:
            # basic info
            serverdict['status'] = server.attrib['status']
            # info is only available if the server is running
            if serverdict['status'] == 'UP':
                serverdict['type'] = 'GAMESERVER'
                serverdict['name'] = server.find('name').text
                for field in ['numplayers', 'maxplayers']:
                    serverdict[field] = int(server.find(field).text)
                # gametype, mod etc
                for rule in server.findall('rules/rule'):
                    if rule.attrib['name'] == "qcstatus":
                        rules = rule.text.split(":")
                        serverdict['gametype'] = rules[0]
                        serverdict['version'] = rules[1]
                        serverdict['mod'] = rules[5][1:].capitalize()
        return server.attrib['address'], serverdict


    def sort_by(self, text):
        keydict = {"Name": 'name', "Current Players": 'numplayers',
                   "Maximum Players": 'maxplayers', "Gametype": 'gametype',
                   "Mod": 'mod'}
        self.sort_serverlist(keydict[text])
        self.sort_favourites(keydict[text])

    def sort_serverlist(self, key='name'):
        # don't sort an empty server list
        if not self.servers:
            return
        # use different sorting for 'numplayers' and 'maxplayers'
        if key in ['numplayers', 'maxplayers']:
            self.servers = OrderedDict(
                sorted(self.servers.items(),
                       key=lambda item: item[1][key], reverse=True))
        else:
            self.servers = OrderedDict(
                sorted(self.servers.items(),
                       key=lambda item: item[1][key].lower()))
        self.update_serverlist()

    def sort_favourites(self, key='name'):
        # don't sort an empty server list
        if not self.fav_servers:
            return
        # use different sorting for 'numplayers' and 'maxplayers'
        if key in ['numplayers', 'maxplayers']:
            self.fav_servers = OrderedDict(
                sorted(self.fav_servers.items(),
                       key=lambda item: item[1][key], reverse=True))
        else:
            self.fav_servers = OrderedDict(
                sorted(self.fav_servers.items(),
                       key=lambda item: item[1][key].lower()))
        self.update_serverlist()

    def update_serverlist(self):
        """
        Update the serverlist. Favourites will always stay on top.
        Only the rest is sorted.
        """
        servers = OrderedDict()
        for address, server in self.fav_servers.items():
            if not self.ids.switch_empty.active and server['numplayers'] == 0:
                continue
            if (not self.ids.switch_full.active and
                server['numplayers'] == server['maxplayers']):
                continue
            if server['status'] == 'UP':
                servers[address] = "[b][i]" + self.serverstring.format(**server) + "[/b][/i]"
            else:
                servers[address] = "[b][i]" + server['name'] + " (NOT REPLYING)[/b][/i]"
        for address, server in self.servers.items():
            if address in self.fav_servers:
                continue
            if not self.ids.switch_empty.active and server['numplayers'] == 0:
                continue
            if (not self.ids.switch_full.active and
                server['numplayers'] == server['maxplayers']):
                continue
            servers[address] = self.serverstring.format(**server)
        self.ids.server_list.adapter.data = servers
        self.ids.server_list.adapter.sorted_keys = servers.keys()


class StarterApp(App):
    title = "Xonotic Starter"
    use_kivy_settings = False

    def start_xon(self, server=None):
        """
        Start Xonotic with the given environment variables and arguments
        Also directly connect to a server if given
        """
        # Environment variables
        myenv = os.environ.copy()
        env_vars = self.config.get("Xonotic", "env_vars")
        if env_vars:
            env_vars = env_vars.split(",")
            for var in env_vars:
                name, value = var.strip().split("=")
                myenv[name] = value

        # Arguments
        args = self.config.get("Xonotic", "args").split()
        # Path and Version like specified in the settings
        xon_path = self.config.get('Xonotic', 'xon_path')
        xon_version = self.config.get('Xonotic', 'xon_version')
        if sys.platform.startswith('linux'):
            xon_script = "xonotic-linux-{}.sh".format(xon_version)
        elif sys.platform in ["win32", "cygwin"]:
            xon_script = "xonotic-windows-{}.bat".format(xon_version)
        elif sys.platform == "darwin":
            xon_script = "Xonotic.app"
        else:
            print "Unsupported platform"
            return

        args.insert(0, os.path.join(xon_path, xon_script))

        if server:
            args.extend(["+connect", server])

        try:
            subprocess.Popen(args, env=myenv)
        except OSError as e:
            content = BoxLayout(orientation='vertical')
            content.add_widget(Label(text="An error occured: " + e.strerror))
            close_btn = Button(text="Close Popup")
            close_btn.size_hint_y = 0.1
            content.add_widget(close_btn)
            popup = Popup(title="Error", content=content)
            close_btn.bind(on_press=popup.dismiss)
            popup.open()

    def build_config(self, config):
        config.setdefaults('Xonotic', {
            'xon_path': "/",
            'env_vars': "",
            'xon_version': "sdl",
            'args': ""})
        config.setdefaults('IRC', {
            'nick': "",
            'username': "",
            'password': ""})

    def build_settings(self, settings):
        settings.add_json_panel('Xonotic', self.config,
                                os.path.join(script_dir(),
                                             'settings_xonotic.json'))
        settings.add_json_panel('IRC', self.config,
                                os.path.join(script_dir(),
                                             'settings_irc.json'))

    def build(self):
        self.icon = os.path.join(self.config.get('Xonotic', 'xon_path'),
                                 "misc/logos/icons_png/xonotic_64.png")
        return MainGUI()


if __name__ == "__main__":
    StarterApp().run()
