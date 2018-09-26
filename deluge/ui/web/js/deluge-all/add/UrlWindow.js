/*!
 * Deluge.add.UrlWindow.js
 *
 * Copyright (c) Damien Churchill 2009-2010 <damoxc@gmail.com>
 *
 * This file is part of Deluge and is licensed under GNU General Public License 3.0, or later, with
 * the additional special exception to link portions of this program with the OpenSSL library.
 * See LICENSE for more details.
 */

Ext.namespace('Deluge.add');
Deluge.add.UrlWindow = Ext.extend(Deluge.add.Window, {

    title: _('Add from Url'),
    modal: true,
    plain: true,
    layout: 'fit',
    width: 350,
    height: 155,

    buttonAlign: 'center',
    closeAction: 'hide',
    bodyStyle: 'padding: 10px 5px;',
    iconCls: 'x-deluge-add-url-window-icon',

    initComponent: function() {
        Deluge.add.UrlWindow.superclass.initComponent.call(this);
        this.addButton(_('Add'), this.onAddClick, this);

        var form = this.add({
            xtype: 'form',
            defaultType: 'textfield',
            baseCls: 'x-plain',
            labelWidth: 55
        });

        this.urlField = form.add({
            fieldLabel: _('Url'),
            id: 'url',
            name: 'url',
            width: '97%'
        });
        this.urlField.on('specialkey', this.onAdd, this);

        this.cookieField = form.add({
            fieldLabel: _('Cookies'),
            id: 'cookies',
            name: 'cookies',
            width: '97%'
        });
        this.cookieField.on('specialkey', this.onAdd, this);
    },

    onAddClick: function(field, e) {
        if ((field.id == 'url' || field.id == 'cookies') && e.getKey() != e.ENTER) return;

        var field = this.urlField;
        var url = field.getValue();
        var cookies = this.cookieField.getValue();
        var torrentId = this.createTorrentId();

        if (url.indexOf('magnet:?') == 0 && url.indexOf('xt=urn:btih') > -1) {
            deluge.client.web.get_magnet_info(url, {
                success: this.onGotInfo,
                scope: this,
                filename: url,
                torrentId: torrentId
            });
            deluge.client.core.prefetch_magnet_metadata(url, {
                success: this.onPrefetchMetadata,
                scope: this,
                filename: url,
            });
        } else {
            deluge.client.web.download_torrent_from_url(url, cookies, {
                success: this.onDownload,
                scope: this,
                torrentId: torrentId
            });
        }

        this.hide();
        this.urlField.setValue('');
        this.fireEvent('beforeadd', torrentId, url);
    },

    onDownload: function(filename, obj, resp, req) {
        deluge.client.web.get_torrent_info(filename, {
            success: this.onGotInfo,
            scope: this,
            filename: filename,
            torrentId: req.options.torrentId
        });
    },

    onPrefetchMetadata: function(result, obj, response, request) {
        // python: infoHash, b64metadata = result
        // metadata = b64decode(b64_metadata)
        if (metadata) {
            deluge.client.web.get_torrent_info(
                null,
                null,
                metadata,
                {
                    success: this.onGotInfo,
                    scope: this,
                    filename: request.options.filename,
                    torrentId: infoHash,
            });
        };
    },

    onGotInfo: function(info, obj, response, request) {
        info['filename'] = request.options.filename;
        this.fireEvent('add', request.options.torrentId, info);
    }
});
