# XonoticSimpleStarter - IRC module
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

from collections import OrderedDict

from kivy.app import App
from kivy.event import EventDispatcher
from kivy.properties import StringProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.treeview import TreeViewLabel
from kivy.lang import Builder

from twisted.internet import protocol, reactor
from twisted.words.protocols import irc


Builder.load_file("ircchannelview.kv")


def colored(text, color):
    colors = OrderedDict([("white", "ffffff"), ("black", "000000"),
                          ("blue", "00007f"), ("green", "009300"),
                          ("red", "ff0000"), ("brown", "7f0000"),
                          ("purple", "9c009c"), ("orange", "fc7f00"),
                          ("yellow", "ffff00"), ("lightgreen", "00fc00"),
                          ("cyan", "009393"), ("lightcyan", "00ffff"),
                          ("lightblue", "0000fc"), ("pink", "ff00ff"),
                          ("grey", "7f7f7f"), ("lightgrey", "d2d2d2")])
    if color not in colors:
        print "Color ", color, " is not available"
        return text
    return "[color={}]{}[/color]".format(colors[color], text)


def bold(text):
    return "[b]{}[/b]".format(text)


def italic(text):
    return "[i]{}[/i]".format(text)


class IRCChannelView(BoxLayout):
    channel = StringProperty("")

    def topicUpdated(self, newTopic):
        # TODO: Color and format information
        self.ids.txt_topic.text = newTopic

    def append_line(self, line):
        self.ids.txt_display.text += line + "\n"

    def append_msg(self, user, msg):
        """
        Append a message to the IRC chat
        """
        # TODO: Color and format information
        self.append_line("{:>20} {}".format(user, msg))

    def append_action(self, user, data):
        self.append_line(colored(italic("{:>20} {}".format(user, data))),
                         "blue")

    def append_notice(self, user, msg):
        self.append_line(colored("{:*>20} {}".format(user, msg), "orange"))

    def on_connected(self):
        self.append_line(colored("Connected", "green"))
        self.ids.btn_join_part.disabled = False

    def on_disconnected(self):
        self.append_line(colored("Disconnected", "red"))
        self.ids.btn_join_part.disabled = True
        self.ids.txt_input.disabled = True
        self.clear_userlist()

    def on_joined(self):
        self.ids.btn_join_part.text = "Part"
        self.append_line(colored("You joined {}".format(self.channel),
                                 "lightgreen"))
        self.ids.txt_input.disabled = False

    def on_left(self):
        self.ids.btn_join_part.text = "Join"
        self.append_line(colored("You left {}".format(self.channel), "red"))
        self.ids.txt_input.disabled = True
        self.clear_userlist()

    def on_kicked(self, message):
        self.ids.btn_join_part.text = "Join"
        self.append_line(colored("You were kicked from {} ({})".format(
            self.channel, message or "No reason given"), "red"))
        self.ids.txt_input.disabled = True
        self.clear_userlist()

    def on_nickChanged(self, oldnick, newnick):
        self.append_line(colored("You are now known as {}".format(newnick),
                                 "lightcyan"))
        self.rename_user_in_tree(oldnick, newnick)

    def on_userJoined(self, user):
        self.append_line(colored("{} joined {}".format(user, self.channel),
                                 "cyan"))
        # new users join as normal users
        # modes are changed after joining
        self.normalusers.append(user)
        self.normalusers.sort(key=str.lower)
        self.update_userlist()

    def on_userKicked(self, kickee, kicker, msg):
        self.append_line(colored("{} was kicked by {} ({})".format(
            kickee, kicker, msg), "brown"))
        self.remove_user_from_tree(kickee)

    def on_userLeft(self, user):
        self.append_line(colored("{} left {}".format(user, self.channel),
                                 "cyan"))
        self.remove_user_from_tree(user)

    def on_userQuit(self, user, msg):
        if user not in self.users:
            return
        self.append_line(colored("{} quit ({})".format(user, msg), "cyan"))
        self.remove_user_from_tree(user)

    def on_userRenamed(self, oldname, newname):
        if oldname not in self.users:
            return
        self.append_line(colored("{} is now known as {}".format(oldname,
                                                                newname),
                         "lightcyan"))
        self.rename_user_in_tree(oldname, newname)

    def on_modeChanged(self, user, set, modes, args):
        user = user.split("!")[0]
        token = "+" if set else "-"
        self.append_line(colored("Mode {}{} for {} by {}".format(
            token, modes, args, user), "cyan"))
        for mode in modes:
            if mode == "o":
                if set:
                    self.users_oped(args)
                else:
                    self.users_deoped(args)
            elif mode == "v":
                if set:
                    self.users_voiced(args)
                else:
                    self.users_devoiced(args)

    @property
    def users(self):
        return self.ops + self.voiced + self.normalusers

    def set_userlist_from_NAMES(self, users):
        """
        Set the userlist after a reply from a NAMES query
        """
        self.clear_userlist()
        for user in users:
            if user.startswith("@"):
                self.ops.append(user[1:])
            elif user.startswith("+"):
                self.voiced.append(user[1:])
            else:
                self.normalusers.append(user)
        self.ops.sort(key=str.lower)
        self.voiced.sort(key=str.lower)
        self.normalusers.sort(key=str.lower)
        self.update_userlist()

    def update_userlist(self):
        """
        Update the list of users in this channel
        """
        self.clear_user_treeview()
        tree = self.ids.tree_users
        root_op = tree.add_node(TreeViewLabel(text="Operators", is_open=True))
        root_voiced = tree.add_node(TreeViewLabel(text="Voiced", is_open=True))
        root_normal = tree.add_node(TreeViewLabel(text="Users", is_open=True))
        for op in self.ops:
            tree.add_node(TreeViewLabel(text=op), root_op)
        for voice in self.voiced:
            tree.add_node(TreeViewLabel(text=voice), root_voiced)
        for user in self.normalusers:
            tree.add_node(TreeViewLabel(text=user), root_normal)

    def clear_userlist(self):
        """
        Clear the userlist completely
        """
        self.ops = []
        self.voiced = []
        self.normalusers = []
        self.clear_user_treeview()

    def clear_user_treeview(self):
        """
        Clear the contents of the userlist treewidget
        """
        tree = self.ids.tree_users
        for node in list(tree.iterate_all_nodes()):
            tree.remove_node(node)

    def remove_user_from_tree(self, user):
        if user in self.ops:
            self.ops.remove(user)
        if user in self.voiced:
            self.voiced.remove(user)
        if user in self.normalusers:
            self.normalusers.remove(user)
        for node in list(self.ids.tree_users.iterate_all_nodes()):
            if node.text == user:
                self.ids.tree_users.remove_node(node)
                break

    def rename_user_in_tree(self, oldname, newname):
        if oldname in self.ops:
            self.ops[self.ops.index(oldname)] = newname
        if oldname in self.voiced:
            self.voiced[self.voiced.index(oldname)] = newname
        if oldname in self.normalusers:
            self.normalusers[self.normalusers.index(oldname)] = newname
        for node in list(self.ids.tree_users.iterate_all_nodes()):
            if node.text == oldname:
                node.text = newname

    def users_oped(self, users):
        for user in users:
            if user in self.normalusers:
                self.normalusers.remove(user)
            elif user in self.voiced:
                self.voiced.remove(user)
            self.ops.append(user)
        self.ops.sort(key=str.lower)
        self.update_userlist()

    def users_deoped(self, users):
        for user in users:
            self.ops.remove(user)
            self.normalusers.append(user)
        self.normalusers.sort(key=str.lower)
        self.update_userlist()

    def users_voiced(self, users):
        for user in users:
            if user in self.normalusers:
                self.normalusers.remove(user)
                self.voiced.append(user)
            # Don't remove the user from ops
        self.voiced.sort(key=str.lower)
        self.update_userlist()

    def users_devoiced(self, users):
        for user in users:
            self.voiced.remove(user)
            self.normalusers.append(user)
        self.normalusers.sort(key=str.lower)
        self.update_userlist()

    def process_text(self, text):
        self.ids.txt_input.text = ""
        text = str(text).strip()
        if not text:
            return
        controller = App.get_running_app().irccontroller
        if not controller.is_connected:
            return
        client = controller.ircfactory.client
        if self.channel not in client.joined_channels:
            return
        client.msg(self.channel, text)
        self.append_msg(client.nickname, text)


class IRCClient(irc.IRCClient):
    def __init__(self):
        self.joined_channels = []
        self.nickname = str(App.get_running_app().config.get('IRC', 'nick'))
        self._userlist = {}

    def auth(self):
        """
        Authenticate if neccessary information is in the config
        """
        config = App.get_running_app().config
        username = config.get('IRC', 'username').strip()
        password = config.get('IRC', 'password').strip()
        service = "Q@CServe.quakenet.org"
        command = "AUTH"
        if username and password:
            print "Authenticating..."
            self.msg(service, "{} {} {}".format(command, username, password))
            self.mode(self.nickname, True, "x")

    def signedOn(self):
        self.factory.controller.is_connected = True
        self.auth()
        if App.get_running_app().config.getboolean('IRC', 'autojoin'):
            self.join("#xonotic")
            self.join("#xonotic.pickup")

    def joined(self, channel):
        print "Joined ", channel
        self.joined_channels.append(channel)
        irc_view = self.factory.controller.get_irc_widget(channel)
        irc_view.on_joined()

    def left(self, channel):
        print "Left", channel
        self.joined_channels.remove(channel)
        # remove the channel from the _userlist
        # use a default value in case the NAMRPLY was not received before
        self._userlist.pop(channel, None)
        irc_view = self.factory.controller.get_irc_widget(channel)
        irc_view.on_left()

    def kickedFrom(self, channel, kicker, msg):
        print "Kicked from ", channel, "by ", kicker
        self.joined_channels.remove(channel)
        # remove the channel from the _userlist
        # use a default value in case the NAMRPLY was not received before
        self._userlist.pop(channel, None)
        irc_view = self.factory.controller.get_irc_widget(channel)
        irc_view.on_kicked(msg)

    def privmsg(self, user, channel, msg):
        if channel not in self.joined_channels:
            print "Message from ", channel, "(", user, "): ", msg
            return
        irc_view = self.factory.controller.get_irc_widget(channel)
        irc_view.append_msg(user.split("!")[0], msg)

    def userJoined(self, user, channel):
        irc_view = self.factory.controller.get_irc_widget(channel)
        irc_view.on_userJoined(user)

    def userKicked(self, kickee, channel, kicker, msg):
        irc_view = self.factory.controller.get_irc_widget(channel)
        irc_view.on_userKicked(kickee, kicker, msg)

    def userLeft(self, user, channel):
        if channel not in self.joined_channels:
            print "Got userLeft message from a channel you have not joined"
            print "This should never happen"
            return
        irc_view = self.factory.controller.get_irc_widget(channel)
        irc_view.on_userLeft(user)

    def userQuit(self, user, quitMessage):
        for channel in self.joined_channels:
            irc_view = self.factory.controller.get_irc_widget(channel)
            irc_view.on_userQuit(user, quitMessage)

    def userRenamed(self, oldname, newname):
        for channel in self.joined_channels:
            irc_view = self.factory.controller.get_irc_widget(channel)
            irc_view.on_userRenamed(oldname, newname)

    def modeChanged(self, user, channel, set, modes, args):
        if channel not in self.joined_channels:
            return
        irc_view = self.factory.controller.get_irc_widget(channel)
        irc_view.on_modeChanged(user, set, modes, args)

    def action(self, user, channel, data):
        if channel not in self.joined_channels:
            print "Action in ", channel, " ", user, " ", data
            return
        irc_view = self.factory.controller.get_irc_widget(channel)
        irc_view.append_action(user.split("!")[0], data)

    def noticed(self, user, channel, msg):
        # Channel will always be your nick or a channel you're in
        if channel in self.joined_channels:
            notice_channels = [channel]
        else:
            notice_channels = self.joined_channels
        for chan in notice_channels:
            irc_view = self.factory.controller.get_irc_widget(chan)
            irc_view.append_notice(user.split("!")[0], msg)

    def nickChanged(self, nick):
        """Triggered when own nick changes"""
        for channel in self.joined_channels:
            irc_view = self.factory.controller.get_irc_widget(channel)
            irc_view.on_nickChanged(self.nickname, nick)
        self.nickname = nick

    def topicUpdated(self, user, channel, newTopic):
        if channel not in self.joined_channels:
            print "Got topic for a channel you have not joined"
            print "This should never happen"
            return
        irc_view = self.factory.controller.get_irc_widget(channel)
        irc_view.topicUpdated(newTopic)

    def irc_RPL_NAMREPLY(self, prefix, params):
        """
        Reply for the NAMES command. Will only be issued when joining a
        channel.
        """
        channel = params[2]
        users = params[3].split()
        if channel not in self.joined_channels:
            print "Received user list for channel: ", channel, ", ignoring it"
            return
        if channel not in self._userlist:
            self._userlist[channel] = users
        else:
            self._userlist[channel].extend(users)

    def irc_RPL_ENDOFNAMES(self, prefix, params):
        channel = params[1]
        if channel not in self.joined_channels:
            print "Received user list for channel: ", channel, ", ignoring it"
            return
        irc_view = self.factory.controller.get_irc_widget(channel)
        irc_view.set_userlist_from_NAMES(self._userlist[channel])


class IRCFactory(protocol.ClientFactory):
    def __init__(self, controller):
        self.controller = controller

    def buildProtocol(self, addr):
        client = IRCClient()
        client.factory = self
        self.client = client
        return client

    def clientConnectionLost(self, connector, reason):
        self.controller.is_connected = False
        print "connection lost ", reason

    def clientConnectionFailed(self, connector, reason):
        self.controller.is_connected = False
        print "connection failed ", reason


class IRCController(EventDispatcher):
    server = "irc.quakenet.org"
    port = 6667
    is_connected = BooleanProperty(False)

    def on_is_connected(self, instance, value):
        maingui = App.get_running_app().root
        irc_ids = [id for id in maingui.ids if id.startswith("irc")]
        if value:
            # enable button
            for id in irc_ids:
                maingui.ids[id].on_connected()
            maingui.ids.btn_connectIRC.text = "Disconnect from IRC"
        else:
            # disable button and input
            for id in irc_ids:
                maingui.ids[id].on_disconnected()
            maingui.ids.btn_connectIRC.text = "Connect to IRC"

    def connect(self):
        if self.is_connected:
            return
        self.ircfactory = IRCFactory(self)
        self.connector = reactor.connectTCP(self.server, self.port,
                                            self.ircfactory)

    def disconnect(self):
        if not self.is_connected:
            return
        self.ircfactory.client.quit()
        self.connector.disconnect()
        self.is_connected = False
        for channel in self.ircfactory.client.joined_channels:
            self.get_irc_widget(channel).ids.btn_join_part.text = "Join"
        self.ircfactory = None

    def toggle_connection(self):
        """
        Toggle the connection to the Quakenet IRC servers
        """
        if not self.is_connected:
            self.connect()
            app = App.get_running_app()
            app.root.ids.btn_connectIRC.text = "Connecting to IRC"
        else:
            self.disconnect()

    def join_or_part(self, channel):
        if not self.is_connected:
            return
        if channel in self.ircfactory.client.joined_channels:
            self.ircfactory.client.leave(channel)
        else:
            self.ircfactory.client.join(channel)

    def get_irc_widget(self, channel):
        maingui = App.get_running_app().root
        irc_ids = [id for id in maingui.ids if id.startswith("irc")]
        for id in irc_ids:
            if maingui.ids[id].channel == channel:
                return maingui.ids[id]
