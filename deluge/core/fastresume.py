# -*- coding: utf-8 -*-
#
# This file is part of Deluge and is licensed under GNU General Public License 3.0, or later, with
# the additional special exception to link portions of this program with the OpenSSL library.
# See LICENSE for more details.
#
from __future__ import unicode_literals

import logging
import os

from twisted.internet import defer, threads
from twisted.internet.defer import Deferred, DeferredList

import deluge.component

log = logging.getLogger(__name__)


class FastResume(object):
    """Handles the loading and saving of torrent fastresume data."""

    def __init__(self, state_dir):
        self.state_dir = state_dir
        self.unified = False
        self.awaiting_torrents = {}
        self.save_resume_data_file_lock = defer.DeferredLock()

    #def save_fastresume(torrent, state_dir):
        # use a sub-directory in state_dir.

    def load_unified(self, torrents):
        """Load the resume data from file for all torrents.

        Returns:
            dict: A dict of torrents and their resume_data.

        """
        filename = 'torrents.fastresume'
        filepath = os.path.join(self.state_dir, filename)
        filepath_bak = filepath + '.bak'
        old_data_filepath = os.path.join(get_config_dir(), filename)

        for _filepath in (filepath, filepath_bak, old_data_filepath):
            log.info('Opening %s for load: %s', filename, _filepath)
            try:
                with open(_filepath, 'rb') as _file:
                    resume_data = lt.bdecode(_file.read())
            except (IOError, EOFError, RuntimeError) as ex:
                if torrents:
                    log.warning('Unable to load %s: %s', _filepath, ex)
                resume_data = None
            else:
                log.info('Successfully loaded %s: %s', filename, _filepath)
                break
        # If the libtorrent bdecode doesn't happen properly, it will return None
        # so we need to make sure we return a {}
        if resume_data is None:
            return {}
        else:
            return resume_data

    def _save_unified_file(self, resume_data):
        """Saves the resume data file with the contents of resume_data"""
        if not resume_data:
            return True

        filename = 'torrents.fastresume'
        filepath = os.path.join(self.state_dir, filename)
        filepath_bak = filepath + '.bak'
        filepath_tmp = filepath + '.tmp'

        try:
            log.debug('Creating the temporary file: %s', filepath_tmp)
            with open(filepath_tmp, 'wb', 0) as _file:
                _file.write(lt.bencode(resume_data))
                _file.flush()
                os.fsync(_file.fileno())
        except (OSError, EOFError) as ex:
            log.error('Unable to save %s: %s', filename, ex)
            return False

        try:
            log.debug('Creating backup of %s at: %s', filename, filepath_bak)
            if os.path.isfile(filepath_bak):
                os.remove(filepath_bak)
            if os.path.isfile(filepath):
                os.rename(filepath, filepath_bak)
        except OSError as ex:
            log.error('Unable to backup %s to %s: %s', filepath, filepath_bak, ex)
            return False

        try:
            log.debug('Saving %s to: %s', filename, filepath)
            os.rename(filepath_tmp, filepath)
        except OSError as ex:
            log.error('Failed to set new file %s: %s', filepath, ex)
            if os.path.isfile(filepath_bak):
                log.info('Restoring backup from: %s', filepath_bak)
                os.rename(filepath_bak, filepath)
        else:
            # Sync the rename operations for the directory
            if hasattr(os, 'O_DIRECTORY'):
                dirfd = os.open(os.path.dirname(filepath), os.O_DIRECTORY)
                os.fsync(dirfd)
                os.close(dirfd)
            return True

    def save(self, queue_task=False, unified=True):
        if not queue_task and self.save_resume_data_file_lock.locked:
            return defer.succeed(None)

        def on_lock_aquired():
            return threads.deferToThread(self._save_unified_file)

        return self.save_resume_data_file_lock.run(on_lock_aquired)

    def build_unified(self, torrent_ids=None, flush_disk_cache=False):
        """Saves torrents resume data.

        Args:
            torrent_ids (list of str): A list of torrents to save the resume data for, defaults
                to None which saves all torrents resume data.
            flush_disk_cache (bool, optional): If True flushes the disk cache which avoids potential
                issue with file timestamps, defaults to False. This is only needed when stopping the session.

        Returns:
            t.i.d.DeferredList: A list of twisted Deferred callbacks to be invoked when save is complete.

        """
        if torrent_ids is None:
            torrent_ids = (tid for tid, t in self.torrents.items() if t.handle.need_save_resume_data())

        def on_torrent_resume_save(dummy_result, torrent_id):
            """Recieved torrent resume_data alert so remove from waiting list"""
            self.awaiting_torrents.pop(torrent_id, None)

        deferreds = []
        for torrent_id in torrent_ids:
            d = self.awaiting_torrents.get(torrent_id)
            if not d:
                d = Deferred().addBoth(on_torrent_resume_save, torrent_id)
                self.awaiting_torrents[torrent_id] = d
            deferreds.append(d)
            self.torrents[torrent_id].save_resume_data(flush_disk_cache)

        def on_all_resume_data_finished(dummy_result):
            """Saves resume data file when no more torrents waiting for resume data.

            Returns:
                bool: True if fastresume file is saved.

                This return value determines removal of `self.temp_file` in `self.stop()`.

            """
            # Use flush_disk_cache as a marker for shutdown so fastresume is
            # saved even if torrents are waiting.
            if not self.awaiting_torrents or flush_disk_cache:
                return self.save_unified(queue_task=flush_disk_cache)

        return DeferredList(deferreds).addBoth(on_all_resume_data_finished)
