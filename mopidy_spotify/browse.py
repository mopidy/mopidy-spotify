from __future__ import unicode_literals

import logging

from mopidy import models

import spotify

from mopidy_spotify import countries, translator


logger = logging.getLogger(__name__)

ROOT_DIR = models.Ref.directory(
    uri='spotify:directory', name='Spotify')

_ROOT_DIR_CONTENTS = [
    models.Ref.directory(
        uri='spotify:top:tracks', name='Top tracks'),
    models.Ref.directory(
        uri='spotify:top:albums', name='Top albums'),
    models.Ref.directory(
        uri='spotify:top:artists', name='Top artists'),
]

_TOPLIST_TYPES = {
    'albums': spotify.ToplistType.ALBUMS,
    'artists': spotify.ToplistType.ARTISTS,
    'tracks': spotify.ToplistType.TRACKS,
}

_TOPLIST_REGIONS = {
    'user': lambda session: spotify.ToplistRegion.USER,
    'country': lambda session: session.user_country,
    'everywhere': lambda session: spotify.ToplistRegion.EVERYWHERE,
}


def browse(config, session, uri):
    if uri == ROOT_DIR.uri:
        return _ROOT_DIR_CONTENTS
    elif uri.startswith('spotify:user:'):
        return _browse_playlist(session, uri)
    elif uri.startswith('spotify:album:'):
        return _browse_album(session, uri)
    elif uri.startswith('spotify:artist:'):
        return _browse_artist(session, uri)
    elif uri.startswith('spotify:top:'):
        parts = uri.replace('spotify:top:', '').split(':')
        if len(parts) == 1:
            return _browse_toplist_regions(variant=parts[0])
        elif len(parts) == 2:
            return _browse_toplist(
                config, session, variant=parts[0], region=parts[1])
        else:
            logger.info(
                'Failed to browse "%s": Toplist URI parsing failed', uri)
            return []
    else:
        logger.info('Failed to browse "%s": Unknown URI type', uri)
        return []


def _browse_playlist(session, uri):
    sp_playlist = session.get_playlist(uri)
    sp_playlist.load()
    return list(translator.to_track_refs(sp_playlist.tracks))


def _browse_album(session, uri):
    sp_album_browser = session.get_album(uri).browse()
    sp_album_browser.load()
    return list(translator.to_track_refs(sp_album_browser.tracks))


def _browse_artist(session, uri):
    sp_artist_browser = session.get_artist(uri).browse(
        type=spotify.ArtistBrowserType.NO_TRACKS)
    sp_artist_browser.load()
    top_tracks = list(translator.to_track_refs(
        sp_artist_browser.tophit_tracks))
    albums = list(translator.to_album_refs(sp_artist_browser.albums))
    return top_tracks + albums


def _browse_toplist_regions(variant):
    return [
        models.Ref.directory(
            uri='spotify:top:%s:user' % variant, name='Personal'),
        models.Ref.directory(
            uri='spotify:top:%s:country' % variant, name='Country'),
        models.Ref.directory(
            uri='spotify:top:%s:countries' % variant,
            name='Other countries'),
        models.Ref.directory(
            uri='spotify:top:%s:everywhere' % variant, name='Global'),
    ]


def _browse_toplist(config, session, variant, region):
    if region == 'countries':
        codes = config['toplist_countries']
        if not codes:
            codes = countries.COUNTRIES.keys()
        return [
            models.Ref.directory(
                uri='spotify:top:%s:%s' % (variant, code.lower()),
                name=countries.COUNTRIES.get(code.upper(), code.upper()))
            for code in codes]

    if region in ('user', 'country', 'everywhere'):
        sp_toplist = session.get_toplist(
            type=_TOPLIST_TYPES[variant],
            region=_TOPLIST_REGIONS[region](session))
    elif len(region) == 2:
        sp_toplist = session.get_toplist(
            type=_TOPLIST_TYPES[variant], region=region.upper())
    else:
        return []

    if session.connection.state is spotify.ConnectionState.LOGGED_IN:
        sp_toplist.load()

    if not sp_toplist.is_loaded:
        return []

    if variant == 'tracks':
        return list(translator.to_track_refs(sp_toplist.tracks))
    elif variant == 'albums':
        return list(translator.to_album_refs(sp_toplist.albums))
    elif variant == 'artists':
        return list(translator.to_artist_refs(sp_toplist.artists))
    else:
        return []
