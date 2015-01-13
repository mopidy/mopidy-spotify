from __future__ import unicode_literals

import logging
import time
import re

from mopidy import backend

import spotify

from mopidy_spotify import translator


logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):

    def __init__(self, backend):
        self._backend = backend

        # TODO Listen to playlist events

    def create(self, name):
        try:
            sp_playlist = (
                self._backend._session.playlist_container
                .add_new_playlist(name))
        except ValueError as exc:
            logger.warning(
                'Failed creating new Spotify playlist "%s": %s', name, exc)
        except spotify.Error:
            logger.warning('Failed creating new Spotify playlist "%s"', name)
        else:
            username = self._backend._session.user_name
            return translator.to_playlist(sp_playlist, username=username)

    def delete(self, uri):
        pass  # TODO

    def lookup(self, uri):
        try:
            sp_playlist = self._backend._session.get_playlist(uri)
        except spotify.Error as exc:
            logger.debug('Failed to lookup Spotify URI %s: %s', uri, exc)
            return

        if not sp_playlist.is_loaded:
            logger.debug(
                'Waiting for Spotify playlist to load: %s', sp_playlist)
            sp_playlist.load()

        username = self._backend._session.user_name
        return translator.to_playlist(
            sp_playlist, username=username, bitrate=self._backend._bitrate)

    @property
    def playlists(self):
        # XXX We should just return light-weight Ref objects here, but Mopidy's
        # core and backend APIs must be changed first.

        if self._backend._session is None:
            return []
        
        offlinecount=self._backend._session.offline.num_playlists
        logger.info("offline playlist count:"+`offlinecount`)
        if offlinecount>0:
	        syncstatus = self._backend._session.offline.sync_status;
		if syncstatus:
		        queued = self._backend._session.offline.sync_status.queued_tracks;
       	 		done = self._backend._session.offline.sync_status.done_tracks;
       	 		errored = self._backend._session.offline.sync_status.error_tracks;
        		logger.info("Offline sync status: Queued="+`queued`+",Done="+`done`+",Error="+`errored`);
                else:
                      	logger.info("Offline sync status: Not syncing")

	        seconds = self._backend._session.offline.time_left;
       	 	logger.info("Time (hours) left until user must go online:"+`seconds/60/60`); 
                
        if self._backend._session.playlist_container is None:
            return []
        
        start = time.time()
        
      
        offlineplaylists = self._backend._config['spotify']['offlinepl']
        trackcounting={}

        username = self._backend._session.user_name
        result = []
        folders = []
	
        for sp_playlist in self._backend._session.playlist_container:
            if isinstance(sp_playlist, spotify.PlaylistFolder):
                if sp_playlist.type is spotify.PlaylistType.START_FOLDER:
                    folders.append(sp_playlist.name)
                elif sp_playlist.type is spotify.PlaylistType.END_FOLDER:
                    folders.pop()
                continue

            playlist = translator.to_playlist(
                sp_playlist, folders=folders, username=username,
                bitrate=self._backend._bitrate)
            if playlist is not None:
                result.append(playlist)
	        logger.info("loaded playlist:"+`playlist.name`+" offline status="+`sp_playlist.offline_status`+" tracks:"+`len(sp_playlist.tracks)`)
                counting={}
                for track in sp_playlist.tracks:     
                    if not track.offline_status in counting:
                        counting[track.offline_status]=1
                    else:
                        counting[track.offline_status]+=1
                    if not track.offline_status in trackcounting:
                        trackcounting[track.offline_status]=1
                    else:
                        trackcounting[track.offline_status]+=1
                        
                offline=False
		for pl in offlineplaylists:
			p = re.compile(pl);
			if p.match(sp_playlist.name):
				offline=True		

		if offline and sp_playlist.offline_status==spotify.PlaylistOfflineStatus.NO:
			logger.info("Offline playlist:"+`sp_playlist.name`+`sp_playlist.offline_status`);
			sp_playlist.set_offline_mode(offline=True);		
		if not offline and sp_playlist.offline_status!=spotify.PlaylistOfflineStatus.NO:
			logger.info("Online playlist:"+`sp_playlist.name`+`sp_playlist.offline_status`);
			sp_playlist.set_offline_mode(offline=False);

        logger.info("Track totals:"+`trackcounting`)
        info = self._backend._session.offline.tracks_to_sync;
        # TODO Add starred playlist

        logger.debug('Playlists fetched in %.3fs', time.time() - start)
        return result

    def refresh(self):
        pass  # Not needed as long as we don't cache anything.

    def save(self, playlist):
        pass  # TODO
