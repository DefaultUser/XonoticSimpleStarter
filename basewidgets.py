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

from kivy.properties import StringProperty
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget
from kivy.lang import Builder


Builder.load_file("basewidgets.kv")


class ScrollableLabel(ScrollView):
    text = StringProperty("")


class HSeparator(Widget):
    pass


class VSeparator(Widget):
    pass
