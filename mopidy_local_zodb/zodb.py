from __future__ import absolute_import, unicode_literals

import collections
import logging
import os
import re
import sys
import time
from copy import deepcopy

import mopidy
from mopidy import local, models
from mopidy.local import search, translator

logger = logging.getLogger(__name__)

import ZODB, ZODB.FileStorage
import BTrees.OOBTree
import transaction


class ZodbLibrary(local.Library):
    name = 'zodb'

    def __init__(self, config):
        self._zodb_file = os.path.join(config['local']['data_dir'], 'library.fs')
        self._added_track_list = [] # for loading only, see .flush()
        self.cache_mpd = config['local-zodb']['cache_mpd']

    def load(self):
        storage = ZODB.FileStorage.FileStorage(self._zodb_file)

        self._db = db = ZODB.DB(storage)
        connection = db.open()
        self._connection = connection
        root = connection.root()
        transaction.begin()

        # Track database
        if not hasattr(root, '_tracks'):
          root._tracks = BTrees.OOBTree.OOBTree()
        self._tracks = root._tracks

        # Cache for browse
        if not hasattr(root, '_browse_cache'):
          root._browse_cache = BTrees.OOBTree.OOBTree()
        self._browse_cache = root._browse_cache

        # Cache for searches.
        # This cache is low level and not so efficient because a list of tracks
        # is pulled from db and then filtered.
        if not hasattr(root, '_search_cache'):
          root._search_cache = BTrees.OOBTree.OOBTree()
        self._search_cache = root._search_cache

        if self.cache_mpd:
          # Cache for mpd queries
          if '_mpd_cache' not in root:
            root['_mpd_cache'] = BTrees.OOBTree.OOBTree()
          self._mpd_cache = root['_mpd_cache']

          # Monkey patch existing MPD commands to add cache
          from mopidy.mpd.protocol import commands
          self._mpd_protocol_handlers = {}
          for name, handler in commands.handlers.items():
            if name in ('count', 'find', 'list',):
              def wrapper(name, original_handler):

                # different MPD clients queries with album cased differently
                lower_case_args = set(('artist', 'album', 'albumartist'))

                def get_cache_key(args):
                  return str((name,) + tuple(
                    (a.lower() in lower_case_args and a.lower() or a)
                    for a in args[1:]))

                def func(*args):
                  cache_key = get_cache_key(args)
                  if cache_key in self._mpd_cache:
                    return self._mpd_cache[cache_key]

                  print "oh pas cache", cache_key
                  value = original_handler(*args)
                  return value

                func.auth_required = original_handler.auth_required
                func.list_command = original_handler.list_command
                func.get_cache_key = get_cache_key
                func.original_handler = original_handler
                return func

              self._mpd_protocol_handlers[name] = \
                commands.handlers[name] = wrapper(name, handler)

        return len(self._tracks)

    def _fill_mpd_cache(self, name, *arguments):
      # To fill MPD cache we need to create a fake context without ourselves as
      # the library.
      from mopidy.mpd.dispatcher import MpdContext
      from mopidy.local.library import LocalLibraryProvider

      class FakeCore:
        class library:
          @staticmethod
          def find_exact(*args, **kw):
            class result:
              @staticmethod
              def get():
                return [self.search(kw, exact=True)]
            return result
        # Instanciating a MpdContext needs to access playlist
        class playlists:
          class playlists:
            @staticmethod
            def get():
              return []

      fake_context = MpdContext(None, core=FakeCore)
      handler = self._mpd_protocol_handlers[name]
      cache_key = handler.get_cache_key((None,) + arguments)
      self._mpd_cache[cache_key] = handler.original_handler(fake_context, *arguments)

    def browse(self, uri):
        return self._browse_cache.get(uri, {}).values()

    def lookup(self, uri):
        try:
            return self._tracks[uri]
        except KeyError:
            return None

    def _fill_search_cache(self, query):
        for exact in (True, False):
          key = '%s %s' % (query, int(exact))
          if key in self._search_cache:
            del self._search_cache[key]
          val = self.search(query, exact=exact)
          self._search_cache[key] = deepcopy(val)

    def search(self, query=None, limit=100, offset=0, uris=None, exact=False):
        assert not uris, NotImplemented
        assert not offset, NotImplemented
        assert limit == 100, NotImplemented
        key = '%s %s' % (query, int(exact))
        try:
          val = self._search_cache[key]
          #print "search hit for ", key
          return val
        except KeyError:
          pass

        tracks = getattr(self, '_tracks', {}).values()
        if exact:
            val = search.find_exact(tracks, query=query, uris=uris)
        else:
            val = search.search(tracks, query=query, uris=uris)
        return val

    # code from mopidy default json library adapted
    encoding = sys.getfilesystemencoding()
    splitpath_re = re.compile(r'([^/]+)')
    def _fill_browser_cache(self, track_uri):
        if 'local:directory' not in self._browse_cache:
          self._browse_cache['local:directory'] = collections.OrderedDict()
        path = translator.local_track_uri_to_path(track_uri, b'/')
        parts = self.splitpath_re.findall(
            path.decode(self.encoding, 'replace'))
        track_ref = models.Ref.track(uri=track_uri, name=parts.pop())

        # Look for our parents backwards as this is faster than having to
        # do a complete search for each add.
        parent_uri = None
        child = None
        for i in reversed(range(len(parts))):
            directory = '/'.join(parts[:i+1])
            uri = translator.path_to_local_directory_uri(directory)

            # First dir we process is our parent
            if not parent_uri:
                parent_uri = uri

            # We found ourselves and we exist, done.
            if uri in self._browse_cache:
                if child:
                    self._browse_cache[uri][child.uri] = child
                break

            # Initialize ourselves, store child if present, and add
            # ourselves as child for next loop.
            self._browse_cache[uri] = collections.OrderedDict()
            if child:
                self._browse_cache[uri][child.uri] = child
            child = models.Ref.directory(uri=uri, name=parts[i])
        else:
            # Loop completed, so final child needs to be added to root.
            if child:
                self._browse_cache['local:directory'][child.uri] = child
            # If no parent was set we belong in the root.
            if not parent_uri:
                parent_uri = 'local:directory'

        self._browse_cache[parent_uri][track_uri] = track_ref
        self._browse_cache._p_changed = 1

    def begin(self):
        return self._tracks.itervalues()

    def add(self, track):
        self._added_track_list.append(track)
        self._tracks[track.uri] = track

    def remove(self, uri):
        track = self._tracks.pop(uri, None)
        self._added_track_list.append(track)

    def flush(self):
        artist_album_set = set()
        for track in self._added_track_list:
          for artist in track.album.artists:
            self._fill_browser_cache(track.uri)
            artist_album_set.add((artist.name, track.album.name))

        for artist, album in artist_album_set:
          if artist:
            self._fill_mpd_cache('list', 'album', 'artist', artist)
            self._fill_mpd_cache('list', 'album', 'albumartist', artist)
            self._fill_mpd_cache('find', 'artist', artist)
            self._fill_mpd_cache('find', 'albumartist', artist)
            self._fill_mpd_cache('list', 'album', artist) # mpdroid queries this
            self._fill_search_cache({'albumartist': [artist]})
            self._fill_search_cache({'artist': [artist]})
          if album:
            self._fill_mpd_cache('list', 'album', album)
            self._fill_mpd_cache('find', 'album', album)
            self._fill_search_cache({'album': [album]})
            if artist:
              self._fill_mpd_cache('find', 'albumartist', artist, 'album', album)
              self._fill_mpd_cache('find', 'album', album, 'albumartist',
              artist)
              self._fill_mpd_cache('find', 'artist', artist, 'album', album)
              self._fill_mpd_cache('count', 'albumartist', artist, 'album', album)
              self._fill_mpd_cache('count', 'album', album, 'albumartist', artist)
              self._fill_mpd_cache('list', 'albumartist', 'artist', artist, 'album', album)
              self._fill_mpd_cache('count', 'artist', artist, 'album', album)
              # mpdroid queries this
              self._fill_mpd_cache('find', 'albumartist', artist, 'album', album, 'track', '1')
              self._fill_mpd_cache('find', 'albumartist', artist, 'album', album, 'track', '01')
              self._fill_search_cache({'album': [album], 'artist': [artist]})
              self._fill_search_cache({'album': [album], 'albumartist': [artist]})

        self._added_track_list = []

        # refresh list all indexes
        self._fill_search_cache({})
        self._fill_mpd_cache('list', 'artist')
        self._fill_mpd_cache('list', 'album')
        self._fill_mpd_cache('list', 'albumartist')

        transaction.commit()
        return True

    def close(self):
        self.flush()
        self._connection.close()
        # Always pack to save disk space. Apparently close is only called
        # during scan
        self._db.pack()
        self._db.close()

    def clear(self):
        self.load()
        self._db.close()
        try:
            os.remove(self._zodb_file)
            self.load()
            return True
        except OSError:
            return False
