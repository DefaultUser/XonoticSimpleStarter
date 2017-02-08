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

from __future__ import print_function

from kivy.app import App
from kivy.lang import Builder
from kivy.support import install_twisted_reactor
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.treeview import TreeViewLabel
from kivy.core.text import LabelBase

from basewidgets import TreeViewContainerNode, WinSettingPath

install_twisted_reactor()

from xml.etree import cElementTree as ElementTree
from twisted.internet import defer, error, reactor
from treq import get

import subprocess
import os
import sys
from collections import OrderedDict

import irc


def script_dir():
    return os.path.dirname(os.path.realpath(sys.argv[0]))


def register_fonts():
    """
    Load additional Fonts
    """
    LabelBase.register(name="xolonium", fn_regular="Xolonium-Regular.otf",
                       fn_bold="Xolonium-Bold.otf",)


def apply_theme(theme):
    """
    Apply a theme specified by theme/<themename>.kv
    """
    if not theme or theme == 'default':
        return
    Builder.load_file("themes/{}.kv".format(theme))


class MainGUI(BoxLayout):
    def ircrules_popup(self):
        IRCRulesPopup().open()


class IRCRulesPopup(Popup):
    ircrules = ("#1: Don't ask to ask - just ask\n#2: Behave as you would do "
                "in a real life conversation\n#3: Be patient - People might "
                "need time to notice your question\n\nMore rules can be "
                "found [color=0000ff][ref=qn-rules]here[/ref][/color]")


class AddFavouritePopup(Popup):
    pass


class StarterWidget(BoxLayout):
    masterserver = "dpmaster.deathmask.net"
    options = "/?game=xonotic&?&xml=1&?&showplayers=1"
    request_url = "http://" + masterserver + options

    def __init__(self, *args, **kwargs):
        self.servers = {}
        self.fav_servers = {}
        self.check_blocked_IPs()
        self.request_info()
        return super(StarterWidget, self).__init__(*args, **kwargs)

    def check_blocked_IPs(self):
        self.blocked_IPs = set()
        xon_path = App.get_running_app().config.get('Xonotic', 'xon_path')
        filepath = os.path.join(xon_path, "misc", "infrastructure",
                                "checkupdate.txt")
        if os.path.isfile(filepath):
            with open(filepath) as f:
                for line in f.readlines():
                    if line.startswith("B"):
                        self.blocked_IPs.add(line[1:].strip())

    def add_favourite(self, name, address):
        if not (name and address):
            print("Input is wrong")
            return False
        if ":" not in address:
            print("Please specify the server by ip:port or domain:port")
            return False
        app = App.get_running_app()
        if not app.config.has_section('Favourites'):
            app.config.add_section('Favourites')
        app.config.set('Favourites', name, address)
        app.config.write()
        return True

    def add_favourite_popup(self, address=None):
        self.popup = AddFavouritePopup()
        self.popup.ids.add_fav_btn.bind(on_press=self.add_fav_btn_callback)
        if address:
            self.popup.ids.txt_inpt_address.text = address
        self.popup.open()

    def add_fav_btn_callback(self, sender):
        name = self.popup.ids.txt_inpt_name.text.strip()
        address = self.popup.ids.txt_inpt_address.text.strip()
        if self.add_favourite(name, address):
            self.popup.dismiss()
            if ":" in address:
                addr, port = address.split(":")
                self.request_serverinfo(addr, port)
            else:
                self.request_serverinfo(address)

    def add_server_to_favourites(self):
        if self.ids.server_list.selected_node:
            server = self.ids.server_list.selected_node.address
            if server not in self.fav_servers.keys():
                self.add_favourite_popup(address=server)

    def connect_to_server(self):
        """
        Get the selected server and connect to it
        """
        if self.ids.server_list.selected_node:
            server = self.ids.server_list.selected_node.address
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
                # domain name and port or IPv4 and port
                if ":" in addr_port:
                    address, port = addr_port.split(":")
                    self.request_serverinfo(address, port)
                # domain name or IPv4 without port
                else:
                    self.request_serverinfo(addr_port)
                self.fav_servers[addr_port] = {'name': name,
                                               'status': 'DOWN',
                                               'numplayers': 0,
                                               'maxplayers': 0,
                                               'gametype': "??",
                                               'mod': "??",
                                               'version': ""}

    @defer.inlineCallbacks
    def request_serverlist(self):
        """
        Request a list of currently public servers from dpmaster.deathmask.net
        """
        try:
            response = yield get(self.request_url, timeout=5)
        except Exception as e:
            print("Requesting serverlist timed out: {}".format(e))
            reactor.callLater(5, self.request_serverlist)
        else:
            xmlstring = yield response.content()
            tree = ElementTree.ElementTree(ElementTree.fromstring(xmlstring))
            root = tree.getroot()

            self.servers = OrderedDict()
            # iterate
            for server in root:
                address, serverdict = self.dictify_server(server)
                if serverdict['type'] == 'MASTERSERVER':
                    print("Number of servers: ", serverdict['numservers'])
                elif serverdict['type'] == 'BLOCKED':
                    print("Blocked server: {}".format(address))
                else:
                    self.servers[address] = serverdict
            # sort the list
            self.sort_by(self.ids.spinner_sort.text)

    @defer.inlineCallbacks
    def request_serverinfo(self, address, port=26000):
        """
        Request info about a specific server from dpmaster.deathmask.net
        """
        url = self.request_url + "&server={}:{}".format(address, port)
        try:
            response = yield get(url, timeout=5)
        except Exception as e:
            print("Requesting serverinfo for server {}:{}"
                  " timed out: {}".format(address, port, e))
            reactor.callLater(5, self.request_serverinfo, address, port)
        else:
            xmlstring = yield response.content()
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
        elif any([server.attrib['address'].startswith(ip) for ip in
                  self.blocked_IPs]):
            serverdict['type'] = 'BLOCKED'
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
                serverdict['gametype'] = "??"
                serverdict['version'] = "??"
                serverdict['mod'] = "??"
                for rule in server.findall('rules/rule'):
                    if rule.attrib['name'] == "qcstatus":
                        rules = rule.text.split(":")
                        try:
                            serverdict['gametype'] = rules[0]
                            serverdict['version'] = rules[1]
                            serverdict['mod'] = rules[5][1:].capitalize()
                        except IndexError:
                            # Some servers do not properly report qcstatus
                            pass
        return server.attrib['address'], serverdict

    def sort_by(self, text):
        keydict = {"Name": 'name', "Current Players": 'numplayers',
                   "Maximum Players": 'maxplayers', "Gametype": 'gametype'}
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
        """
        self.clear_serverlist()
        tree = self.ids.server_list
        filter_str = self.ids.txt_input_filter.text.strip().lower()
        servers = OrderedDict()
        for address, server in self.fav_servers.items():
            if filter_str not in server['name'].lower():
                continue
            if not self.ids.switch_empty.active and server['numplayers'] == 0:
                continue
            if (not self.ids.switch_full.active and
                    server['numplayers'] == server['maxplayers']):
                continue
            node = TreeViewContainerNode(height=32)
            node.add_widget(Label(text="[b]{}[/b]".format(server['name']),
                                  size_hint_x=0.6))
            node.add_widget(Label(text="{} ({})".format(server['gametype'],
                                                        server['mod']),
                                  size_hint_x=0.2))
            node.add_widget(Label(text="{}/{}".format(server['numplayers'],
                                                      server['maxplayers']),
                                  size_hint_x=0.2))
            tree.add_node(node, self.servertype_nodes['fav'])
            node.address = address
        for address, server in self.servers.items():
            if address in self.fav_servers:
                continue
            if filter_str not in server['name'].lower():
                continue
            if not self.ids.switch_empty.active and server['numplayers'] == 0:
                continue
            if (not self.ids.switch_full.active and
                    server['numplayers'] == server['maxplayers']):
                continue
            if server['mod'] in ('Xonotic', 'Xpm'):
                parent = self.servertype_nodes['vanilla']
            elif server['mod'] == 'Instagib':
                parent = self.servertype_nodes['insta']
            elif server['mod'] == 'Overkill':
                parent = self.servertype_nodes['ok']
            elif server['mod'] == 'Xdf':
                parent = self.servertype_nodes['xdf']
            else:
                parent = self.servertype_nodes['other']
            node = TreeViewContainerNode(height=32)
            node.add_widget(Label(text=server['name'], size_hint_x=0.6))
            node.add_widget(Label(text="{} ({})".format(server['gametype'],
                                                        server['mod']),
                                  size_hint_x=0.2))
            node.add_widget(Label(text="{}/{}".format(server['numplayers'],
                                                      server['maxplayers']),
                                  size_hint_x=0.2))
            tree.add_node(node, parent)
            node.address = address

    def clear_serverlist(self):
        tree = self.ids.server_list
        for node in list(tree.iterate_all_nodes()):
            tree.remove_node(node)

        nodes = {}
        nodes['fav'] = tree.add_node(TreeViewLabel(text="Favourites",
                                                   is_open=True,
                                                   no_selection=True))
        nodes['vanilla'] = tree.add_node(TreeViewLabel(text="All Weapons",
                                                       is_open=True,
                                                       no_selection=True))
        nodes['insta'] = tree.add_node(TreeViewLabel(text="Instagib",
                                                     is_open=True,
                                                     no_selection=True))
        nodes['ok'] = tree.add_node(TreeViewLabel(text="Overkill",
                                                  is_open=True,
                                                  no_selection=True))
        nodes['xdf'] = tree.add_node(TreeViewLabel(text="XDF",
                                                   is_open=True,
                                                   no_selection=True))
        nodes['other'] = tree.add_node(TreeViewLabel(text="Other",
                                                     is_open=True,
                                                     no_selection=True))
        self.servertype_nodes = nodes


class StarterApp(App):
    title = "Xonotic Starter"
    use_kivy_settings = False

    def on_start(self):
        self.irccontroller = irc.IRCController()

    def on_stop(self):
        # Disconnect from IRC if window is destroyed
        self.irccontroller.disconnect()

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
        # git version
        if os.path.isfile(os.path.join(xon_path, "all")):
            xon_app = "all"
            args.insert(0, "run")
            args.insert(1, xon_version)
        # release and autobuild versions
        elif sys.platform.startswith('linux'):
            xon_app = "xonotic-linux-{}.sh".format(xon_version)
        elif sys.platform in ["win32", "cygwin"]:
            if xon_version == "sdl":
                xon_app = "xonotic.exe"
            else:
                xon_app = "xonotic-wgl.exe"
            args.extend(["-basedir", xon_path])
        elif sys.platform == "darwin":
            xon_app = "Xonotic.app"
        else:
            print("Unsupported platform")
            return

        args.insert(0, os.path.join(xon_path, xon_app))

        if server:
            args.extend(["+connect", server])

        try:
            subprocess.Popen(args, cwd=xon_path, env=myenv)
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
            'xon_path': script_dir(),
            'env_vars': "",
            'xon_version': "sdl",
            'args': ""})
        config.setdefaults('IRC', {
            'nick': "XonoticFan",
            'username': "",
            'password': "",
            'autojoin': False})

    def build_settings(self, settings):
        settings.register_type('winPath', WinSettingPath)
        settings.add_json_panel('Xonotic', self.config,
                                os.path.join(script_dir(),
                                             'settings_xonotic.json'))
        settings.add_json_panel('IRC', self.config,
                                os.path.join(script_dir(),
                                             'settings_irc.json'))

    def build(self):
        self.icon = os.path.join(self.config.get('Xonotic', 'xon_path'),
                                 "misc/logos/icons_png/xonotic_64.png")
        register_fonts()
        apply_theme("luma")
        return MainGUI()


if __name__ == "__main__":
    StarterApp().run()
