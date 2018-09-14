# -*- coding: utf-8 -*-
#
# Copyright (C) 2018 Calum Lind <calumlind+deluge@gmail.com>
#
# This file is part of Deluge and is licensed under GNU General Public License
# 3.0, or later, with the additional special exception to link portions of this
# program with the OpenSSL library. See LICENSE for more details.
#


from __future__ import division, unicode_literals

import logging
import os
from base64 import b64encode
from xml.sax.saxutils import escape as xml_escape
from xml.sax.saxutils import unescape as xml_unescape

import gtk
from gobject import TYPE_INT64, TYPE_UINT64

import deluge.common
import deluge.component as component
from deluge.configmanager import ConfigManager
from deluge.httpdownloader import download_file
from deluge.ui.client import client
from deluge.ui.common import TorrentInfo
from deluge.ui.gtkui.common import get_clipboard_text, listview_replace_treestore, reparent_iter
from deluge.ui.gtkui.dialogs import ErrorDialog
from deluge.ui.gtkui.edittrackersdialog import trackers_tiers_from_text
from deluge.ui.gtkui.path_chooser import PathChooser
from deluge.ui.gtkui.torrentview_data_funcs import cell_data_size

log = logging.getLogger(__name__)


class FindReplaceTrackersDialog(component.Component):
    def __init__(self):
        component.Component.__init__(self, 'FindReplaceTrackersDialog')
        self.builder = gtk.Builder()
        self.builder.add_from_file(deluge.common.resource_filename(
            'deluge.ui.gtkui',
            os.path.join('glade', 'find_replace_trackers.ui'),
        ))
        self.replace_dialog = self.builder.get_object(
            'find_replace_trackers_dialog')
        self.builder.connect_signals(self)
        self.replace_dialog.set_transient_for(
            component.get('MainWindow').window)
        self.search_str = None
        self.replace_str = None

    def on_torrent_status(self, result):
        for torrent_id, status in result.items():
            log.critical('%s %s', torrent_id, status['trackers'][0]['url'])

    def on_replace_button_clicked(self, widget):
        self.search_str = self.builder.get_object('search_entry').get_text()
        self.replace_str = self.builder.get_object('replace_entry').get_text()

        if not self.search_str:
            return

        component.get('SessionProxy').get_torrents_status(
            {}, ['trackers']).addCallback(self.on_torrent_status)

    def on_close_button_clicked(self, widget):
        self.replace_dialog.hide()

    def show(self):
        """Show the dialog."""
        self.replace_dialog.show()
