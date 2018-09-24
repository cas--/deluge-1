#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2013 Bro <bro.development@gmail.com>
#
# This file is part of Deluge and is licensed under GNU General Public License 3.0, or later, with
# the additional special exception to link portions of this program with the OpenSSL library.
# See LICENSE for more details.
#

from __future__ import unicode_literals

import ctypes
import os

from deluge.common import PY2, windows_check


def is_hidden(filepath):
    def has_hidden_attribute(filepath):
        if not windows_check():
            return False

        try:
            if not PY2:
                attrs = os.stat(filepath).st_file_attributes
            else:
                attrs = ctypes.windll.kernel32.GetFileAttributesW(filepath)
            assert attrs != -1
            # FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM
            result = bool(attrs & (2 | 4))
        except (AttributeError, AssertionError):
            result = False
        return result

    name = os.path.basename(os.path.abspath(filepath))
    return name.startswith('.') or has_hidden_attribute(filepath)


def get_completion_paths(args):
    """
    Takes a path value and returns the available completions.
    If the path_value is a valid path, return all sub-directories.
    If the path_value is not a valid path, remove the basename from the
    path and return all sub-directories of path that start with basename.

    :param args: options
    :type args: dict
    :returns: the args argument containing the available completions for the completion_text
    :rtype: list

    """
    args['paths'] = []
    path_value = args['completion_text']
    hidden_files = args['show_hidden_files']

    def get_subdirs(dirname):
        try:
            return os.walk(dirname).next()[1]
        except StopIteration:
            # Invalid dirname
            return []

    dirname = os.path.dirname(path_value)
    basename = os.path.basename(path_value)

    dirs = get_subdirs(dirname)
    # No completions available
    if not dirs:
        return args

    # path_value ends with path separator so
    # we only want all the subdirectories
    if not basename:
        # Lets remove hidden files
        if not hidden_files:
            old_dirs = dirs
            dirs = []
            for d in old_dirs:
                if not is_hidden(os.path.join(dirname, d)):
                    dirs.append(d)
    matching_dirs = []
    for s in dirs:
        if s.startswith(basename):
            p = os.path.join(dirname, s)
            if not p.endswith(os.path.sep):
                p += os.path.sep
            matching_dirs.append(p)

    args['paths'] = sorted(matching_dirs)
    return args
