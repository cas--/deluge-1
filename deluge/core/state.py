# -*- coding: utf-8 -*-
#
# Copyright (C) 2007-2009 Andrew Resch <andrewresch@gmail.com>
#
# This file is part of Deluge and is licensed under GNU General Public License 3.0, or later, with
# the additional special exception to link portions of this program with the OpenSSL library.
# See LICENSE for more details.
#
"""
This module is for saving the Deluge state, specifically Torrent and
TorrentManager states. This is data that is usually not stored by libtorrent
in the resume data.
"""
from __future__ import unicode_literals

import cPickle as pickle
import logging
import os

from twisted.internet import defer, threads

import deluge.component

log = logging.getLogger(__name__)


class TorrentState:  # pylint: disable=old-style-class
    """Create a torrent state.

    Note:
        This must be old style class to avoid breaking torrent.state file.

    """
    def __init__(self,
                 torrent_id=None,
                 filename=None,
                 trackers=None,
                 storage_mode='sparse',
                 paused=False,
                 save_path=None,
                 max_connections=-1,
                 max_upload_slots=-1,
                 max_upload_speed=-1.0,
                 max_download_speed=-1.0,
                 prioritize_first_last=False,
                 sequential_download=False,
                 file_priorities=None,
                 queue=None,
                 auto_managed=True,
                 is_finished=False,
                 stop_ratio=2.00,
                 stop_at_ratio=False,
                 remove_at_ratio=False,
                 move_completed=False,
                 move_completed_path=None,
                 magnet=None,
                 owner=None,
                 shared=False,
                 super_seeding=False,
                 name=None):
        # Build the class atrribute list from args
        for key, value in locals().items():
            if key == 'self':
                continue
            setattr(self, key, value)

    def __eq__(self, other):
        return isinstance(other, TorrentState) and self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self == other


class TorrentManagerState:  # pylint: disable=old-style-class
    """TorrentManagerState holds a list of TorrentState objects.

    Note:
        This must be old style class to avoid breaking torrent.state file.

    """
    def __init__(self):
        self.torrents = []

    def __eq__(self, other):
        return (
            isinstance(other, TorrentManagerState)
            and self.torrents == other.torrents
        )

    def __ne__(self, other):
        return not self == other


class State(object):
    """Save and loads the session torrent state to file"""

    def __init__(self, state_dir):
        self.state_dir = state_dir
        self.prev_saved_state = None
        self.is_saving = False

    @staticmethod
    def fixup(state):
        """Fixup an old state by adding missing TorrentState options and assigning default values.

        Args:
            state (TorrentManagerState): A torrentmanager state containing torrent details.

        Returns:
            TorrentManagerState: A fixedup TorrentManager state.

        """
        if state.torrents:
            t_state_tmp = TorrentState()
            if dir(state.torrents[0]) != dir(t_state_tmp):
                try:
                    for attr in set(dir(t_state_tmp)) - set(dir(state.torrents[0])):
                        for t_state in state.torrents:
                            setattr(t_state, attr, getattr(t_state_tmp, attr, None))
                except AttributeError as ex:
                    log.error('Unable to update state file to a compatible version: %s', ex)
        return state

    @staticmethod
    def _create(torrents):
        """Create a state of all the torrents.

        Returns:
            TorrentManagerState: The state containing torrent states.

        """
        state = TorrentManagerState()
        # Create the state for each Torrent and append to the list
        session_paused = deluge.component.get('Core').session.is_paused()
        for torrent in torrents.values():
            if session_paused:
                paused = torrent.handle.is_paused()
            elif torrent.forced_error:
                paused = torrent.forced_error.was_paused
            elif torrent.state == 'Paused':
                paused = True
            else:
                paused = False

            torrent_state = TorrentState(
                torrent.torrent_id,
                torrent.filename,
                torrent.trackers,
                torrent.get_status(['storage_mode'])['storage_mode'],
                paused,
                torrent.options['download_location'],
                torrent.options['max_connections'],
                torrent.options['max_upload_slots'],
                torrent.options['max_upload_speed'],
                torrent.options['max_download_speed'],
                torrent.options['prioritize_first_last_pieces'],
                torrent.options['sequential_download'],
                torrent.options['file_priorities'],
                torrent.get_queue_position(),
                torrent.options['auto_managed'],
                torrent.is_finished,
                torrent.options['stop_ratio'],
                torrent.options['stop_at_ratio'],
                torrent.options['remove_at_ratio'],
                torrent.options['move_completed'],
                torrent.options['move_completed_path'],
                torrent.magnet,
                torrent.options['owner'],
                torrent.options['shared'],
                torrent.options['super_seeding'],
                torrent.options['name']
            )
            state.torrents.append(torrent_state)
        return state

    def _save(self, torrents):
        """Save the state of the TorrentManager to the torrents.state file."""
        state = self._create_state(torrents, self.state_dir)
        if not state.torrents:
            log.debug('Skipping saving state with no torrents loaded')
            return

        # If the state hasn't changed, no need to save it
        if self.prev_saved_state == state:
            return

        filename = 'torrents.state'
        filepath = os.path.join(self.state_dir, filename)
        filepath_bak = filepath + '.bak'
        filepath_tmp = filepath + '.tmp'

        log.debug('Creating the temporary file: %s', filepath_tmp)
        try:
            with open(filepath_tmp, 'wb', 0) as _file:
                pickle.dump(state, _file)
                _file.flush()
                os.fsync(_file.fileno())
        except (OSError, pickle.PicklingError) as ex:
            log.error('Unable to save %s: %s', filename, ex)
            return

        log.debug('Creating backup of %s at: %s', filename, filepath_bak)
        try:
            if os.path.isfile(filepath_bak):
                os.remove(filepath_bak)
            if os.path.isfile(filepath):
                os.rename(filepath, filepath_bak)
        except OSError as ex:
            log.error('Unable to backup %s to %s: %s', filepath, filepath_bak, ex)
            return

        log.debug('Saving %s to: %s', filename, filepath)
        try:
            os.rename(filepath_tmp, filepath)
        except OSError as ex:
            log.error('Failed to set new state file %s: %s', filepath, ex)
            if os.path.isfile(filepath_bak):
                log.info('Restoring backup of state from: %s', filepath_bak)
                os.rename(filepath_bak, filepath)

    def save(self, torrents):
        if self.is_saving:
            return defer.succeed(None)
        self.is_saving = True

        def on_saved(result):
            self.is_saving = False
            return defer.succeed(result)

        return threads.deferToThread(self._save, torrents).addBoth(on_saved)

    def load(self):
        """Load the torrents.state file containing a TorrentManager state with session torrents.

        Returns:
            TorrentManagerState: The TorrentManager state.

        """
        torrents_state = os.path.join(self.state_dir, 'torrents.state')
        for filepath in (torrents_state, torrents_state + '.bak'):
            log.info('Loading torrent state: %s', filepath)
            try:
                with open(filepath, 'rb') as _file:
                    state = pickle.load(_file)
            except (IOError, EOFError, pickle.UnpicklingError) as ex:
                log.warning('Unable to load %s: %s', filepath, ex)
                state = None
            else:
                log.info('Successfully loaded %s', filepath)
                break

        if state is None:
            state = TorrentManagerState()
        return self.fixup(state)
