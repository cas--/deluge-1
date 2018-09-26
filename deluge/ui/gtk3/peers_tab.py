# -*- coding: utf-8 -*-
#
# Copyright (C) 2008 Andrew Resch <andrewresch@gmail.com>
#
# This file is part of Deluge and is licensed under GNU General Public License 3.0, or later, with
# the additional special exception to link portions of this program with the OpenSSL library.
# See LICENSE for more details.
#

from __future__ import unicode_literals

import logging
import os.path

from gi.repository import Gtk, Gdk
from gi.repository.GdkPixbuf import Pixbuf
from gi.repository.Gtk import (Builder, CellRendererPixbuf, CellRendererProgress, CellRendererText, ListStore,
                               TreeViewColumn, TreeViewColumnSizing)
import cairo

import deluge.common
import deluge.component as component
from deluge.ui.client import client
from deluge.ui.countries import COUNTRIES

from .common import icon_downloading, icon_seeding, load_pickled_state_file, save_pickled_state_file
from .torrentdetails import Tab
from .torrentview_data_funcs import cell_data_peer_progress, cell_data_speed_down, cell_data_speed_up

try:
    from future_builtins import zip
except ImportError:
    # Ignore on Py3.
    pass

log = logging.getLogger(__name__)

scale = component.get('MainWindow').window.get_scale_factor()


class PeersTab(Tab):
    def __init__(self):
        super(PeersTab, self).__init__('Peers', 'peers_tab', 'peers_tab_label')

        self.peer_menu = self.main_builder.get_object('menu_peer_tab')
        component.get('MainWindow').connect_signals(self)

        self.listview = self.main_builder.get_object('peers_listview')
        self.listview.props.has_tooltip = True
        self.listview.connect('button-press-event', self._on_button_press_event)
        self.listview.connect('query-tooltip', self._on_query_tooltip)

        # flag, ip, client, downspd, upspd, country code, int_ip, seed/peer icon, progress
        self.liststore = ListStore(Pixbuf, str, str, int, int, str, float, str, float)
        self.cached_flag_pixbufs = {}

        self.seed_pixbuf = icon_seeding
        self.peer_pixbuf = icon_downloading

        # key is ip address, item is row iter
        self.peers = {}

        # Country column
        column = TreeViewColumn()
        render = CellRendererPixbuf()
        column.pack_start(render, False)
        column.set_cell_data_func(render, self.cell_flag_icon, 5)
        column.set_sort_column_id(5)
        column.set_clickable(True)
        column.set_resizable(True)
        column.set_expand(False)
        column.set_min_width(40)
        column.set_reorderable(True)
        self.listview.append_column(column)

        # Address column
        column = TreeViewColumn(_('Address'))
        render = CellRendererPixbuf()
        column.pack_start(render, False)
        column.add_attribute(render, 'icon-name', 7)
        render = CellRendererText()
        column.pack_start(render, False)
        column.add_attribute(render, 'text', 1)
        column.set_sort_column_id(6)
        column.set_clickable(True)
        column.set_resizable(True)
        column.set_expand(False)
        column.set_min_width(100)
        column.set_reorderable(True)
        self.listview.append_column(column)

        # Client column
        column = TreeViewColumn(_('Client'))
        render = CellRendererText()
        column.pack_start(render, False)
        column.add_attribute(render, 'text', 2)
        column.set_sort_column_id(2)
        column.set_clickable(True)
        column.set_resizable(True)
        column.set_expand(False)
        column.set_min_width(100)
        column.set_reorderable(True)
        self.listview.append_column(column)

        # Progress column
        column = TreeViewColumn(_('Progress'))
        render = CellRendererProgress()
        render.set_padding(0, 1)
        column.pack_start(render, True)
        column.set_cell_data_func(render, cell_data_peer_progress, 8)
        column.set_sort_column_id(8)
        column.set_clickable(True)
        column.set_resizable(True)
        column.set_expand(False)
        column.set_min_width(100)
        column.set_reorderable(True)
        self.listview.append_column(column)

        # Down Speed column
        column = TreeViewColumn(_('Down Speed'))
        render = CellRendererText()
        column.pack_start(render, False)
        column.set_cell_data_func(render, cell_data_speed_down, 3)
        column.set_sort_column_id(3)
        column.set_clickable(True)
        column.set_resizable(True)
        column.set_expand(False)
        column.set_min_width(50)
        column.set_reorderable(True)
        self.listview.append_column(column)

        # Up Speed column
        column = TreeViewColumn(_('Up Speed'))
        render = CellRendererText()
        column.pack_start(render, False)
        column.set_cell_data_func(render, cell_data_speed_up, 4)
        column.set_sort_column_id(4)
        column.set_clickable(True)
        column.set_resizable(True)
        column.set_expand(False)
        column.set_min_width(50)
        # Bugfix: Last column needs max_width set to stop scrollbar appearing
        column.set_max_width(150)
        column.set_reorderable(True)
        self.listview.append_column(column)

        self.listview.set_model(self.liststore)

        self.load_state()

        self.torrent_id = None

    def save_state(self):
        # Get the current sort order of the view
        column_id, sort_order = self.liststore.get_sort_column_id()

        # Setup state dict
        state = {
            'columns': {},
            'sort_id': column_id,
            'sort_order': int(sort_order) if sort_order else None,
        }

        for index, column in enumerate(self.listview.get_columns()):
            state['columns'][column.get_title()] = {
                'position': index,
                'width': column.get_width(),
            }
        save_pickled_state_file('peers_tab.state', state)

    def load_state(self):
        state = load_pickled_state_file('peers_tab.state')

        if state is None:
            return

        if len(state['columns']) != len(self.listview.get_columns()):
            log.warning('peers_tab.state is not compatible! rejecting..')
            return

        if state['sort_id'] and state['sort_order'] is not None:
            self.liststore.set_sort_column_id(state['sort_id'], state['sort_order'])

        for (index, column) in enumerate(self.listview.get_columns()):
            cname = column.get_title()
            if cname in state['columns']:
                cstate = state['columns'][cname]
                column.set_sizing(TreeViewColumnSizing.FIXED)
                column.set_fixed_width(cstate['width'] if cstate['width'] > 0 else 10)
                if state['sort_id'] == index and state['sort_order'] is not None:
                    column.set_sort_indicator(True)
                    column.set_sort_order(state['sort_order'])
                if cstate['position'] != index:
                    # Column is in wrong position
                    if cstate['position'] == 0:
                        self.listview.move_column_after(column, None)
                    elif self.listview.get_columns()[cstate['position'] - 1].get_title() != cname:
                        self.listview.move_column_after(column, self.listview.get_columns()[cstate['position'] - 1])

    def update(self):
        # Get the first selected torrent
        torrent_id = component.get('TorrentView').get_selected_torrents()

        # Only use the first torrent in the list or return if None selected
        if len(torrent_id) != 0:
            torrent_id = torrent_id[0]
        else:
            # No torrent is selected in the torrentview
            self.liststore.clear()
            return

        if torrent_id != self.torrent_id:
            # We only want to do this if the torrent_id has changed
            self.liststore.clear()
            self.peers = {}
            self.torrent_id = torrent_id

        component.get('SessionProxy').get_torrent_status(torrent_id, ['peers']).addCallback(self._on_get_torrent_status)

    def get_flag_pixbuf(self, country):
        if not country.strip():
            return None

        if country not in self.cached_flag_pixbufs:
            # We haven't created a pixbuf for this country yet
            try:
                self.cached_flag_pixbufs[country] = Pixbuf.new_from_file_at_scale(
                    deluge.common.resource_filename(
                        'deluge',
                        os.path.join('ui', 'data', 'pixmaps', 'flags', country.lower() + '.svgz'),
                    ), -1, 16 * scale, True
                )
            except Exception as ex:
                log.debug('Unable to load flag: %s', ex)
                return None

        return self.cached_flag_pixbufs[country]

    def _on_get_torrent_status(self, status):
        new_ips = set()
        for peer in status['peers']:
            new_ips.add(peer['ip'])
            if peer['ip'] in self.peers:
                # We already have this peer in our list, so lets just update it
                row = self.peers[peer['ip']]
                if not self.liststore.iter_is_valid(row):
                    # This iter is invalid, delete it and continue to next iteration
                    del self.peers[peer['ip']]
                    continue
                values = self.liststore.get(row, 3, 4, 5, 7, 8)
                if peer['down_speed'] != values[0]:
                    self.liststore.set_value(row, 3, peer['down_speed'])
                if peer['up_speed'] != values[1]:
                    self.liststore.set_value(row, 4, peer['up_speed'])
                if peer['country'] != values[2]:
                    self.liststore.set_value(row, 5, peer['country'])
                if peer['seed']:
                    icon = self.seed_pixbuf
                else:
                    icon = self.peer_pixbuf

                if icon != values[3]:
                    self.liststore.set_value(row, 7, icon)

                if peer['progress'] != values[4]:
                    self.liststore.set_value(row, 8, peer['progress'])
            else:
                # Peer is not in list so we need to add it

                # Create an int IP address for sorting purposes
                if peer['ip'].count(':') == 1:
                    # This is an IPv4 address
                    ip_int = sum(
                        int(byte) << shift
                        for byte, shift in zip(peer['ip'].split(':')[0].split('.'), (24, 16, 8, 0))
                    )
                    peer_ip = peer['ip']
                else:
                    # This is an IPv6 address
                    import socket
                    import binascii
                    # Split out the :port
                    ip = ':'.join(peer['ip'].split(':')[:-1])
                    ip_int = int(binascii.hexlify(socket.inet_pton(socket.AF_INET6, ip)), 16)
                    peer_ip = '[%s]:%s' % (ip, peer['ip'].split(':')[-1])

                if peer['seed']:
                    icon = self.seed_pixbuf
                else:
                    icon = self.peer_pixbuf

                row = self.liststore.append([
                    self.get_flag_pixbuf(peer['country']),
                    peer_ip,
                    peer['client'],
                    peer['down_speed'],
                    peer['up_speed'],
                    peer['country'],
                    float(ip_int),
                    icon,
                    peer['progress'],
                ])

                self.peers[peer['ip']] = row

        # Now we need to remove any ips that were not in status["peers"] list
        for ip in set(self.peers).difference(new_ips):
            self.liststore.remove(self.peers[ip])
            del self.peers[ip]

    def clear(self):
        self.liststore.clear()

    def _on_button_press_event(self, widget, event):
        """This is a callback for showing the right-click context menu."""
        log.debug('on_button_press_event')
        # We only care about right-clicks
        if self.torrent_id and event.button == 3:
            self.peer_menu.popup(None, None, None, None, event.button, event.time)
            return True

    def _on_query_tooltip(self, widget, x, y, keyboard_tip, tooltip):

        def on_draw(wid, cr):
            cr.scale(float(wid.get_allocated_width()) / float(pix.get_width()),
                     float(wid.get_allocated_height()) / float(pix.get_height()))
            Gdk.cairo_set_source_pixbuf(cr, pix, 0, 0)
            cr.paint_with_alpha(0.8)

        tooltip_row, x, y, model, path, _iter = widget.get_tooltip_context(
            x, y, keyboard_tip)
        if tooltip_row:
            column = widget.get_path_at_pos(x, y)[1]
            if column.get_title() == '':
                country_code = model.get_value(_iter, 5)
                if country_code != '  ' and country_code in COUNTRIES:
                    box = Gtk.Box(Gtk.Orientation.HORIZONTAL, 4)
                    draw_area = Gtk.DrawingArea()
                    draw_area.connect("draw", on_draw)
                    pix = Pixbuf.new_from_file(
                        deluge.common.resource_filename(
                            'deluge',
                            os.path.join('ui', 'data', 'pixmaps', 'flags', country_code.lower() + '.svgz'),
                        ))
                    req_icon_height = 64
                    draw_area.set_size_request(req_icon_height * pix.get_width() / pix.get_height(), req_icon_height)
                    text = Gtk.Label()
                    text.set_markup('<b>%s</b>' % COUNTRIES[country_code])
                    box.add(draw_area)
                    box.add(text)
                    box.show_all()
                    tooltip.set_custom(box)
                    # widget here is self.listview
                    widget.set_tooltip_cell(
                        tooltip, path, column,
                        None,
                    )
                    return True
        return False

    def on_menuitem_add_peer_activate(self, menuitem):
        """This is a callback for manually adding a peer"""
        log.debug('on_menuitem_add_peer')
        builder = Builder()
        builder.add_from_file(deluge.common.resource_filename(
            __package__, os.path.join('glade', 'connect_peer_dialog.ui'),
        ))
        peer_dialog = builder.get_object('connect_peer_dialog')
        txt_ip = builder.get_object('txt_ip')
        response = peer_dialog.run()
        if response:
            value = txt_ip.get_text()
            if value and ':' in value:
                if ']' in value:
                    # ipv6
                    ip = value.split(']')[0][1:]
                    port = value.split(']')[1][1:]
                else:
                    # ipv4
                    ip = value.split(':')[0]
                    port = value.split(':')[1]
                if deluge.common.is_ip(ip):
                    log.debug('adding peer %s to %s', value, self.torrent_id)
                    client.core.connect_peer(self.torrent_id, ip, port)
        peer_dialog.destroy()
        return True

    def cell_flag_icon(self, column, cell, model, row, data):
        country = self.liststore.get_value(row, 5)
        pix = self.get_flag_pixbuf(country)
        if not pix:
            return

        w = pix.get_width()
        h = pix.get_height()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
        surface.set_device_scale(scale, scale)
        cr = cairo.Context(surface)
        cr.scale(1.0 / scale, 1.0 / scale)
        Gdk.cairo_set_source_pixbuf(cr, pix, 0, 0)
        cr.paint_with_alpha(0.8)
        cr.rectangle(0, 0, w, h)
        cr.set_source_rgba(0.3, 0.3, 0.3, 1)
        cr.set_line_width(scale)
        cr.stroke()

        cell.set_property("surface", surface)

