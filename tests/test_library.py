from __future__ import unicode_literals

import shutil
import tempfile
import unittest

from mopidy.local import translator
from mopidy.models import SearchResult, Track, Artist, Album

from mopidy_local_zodb import zodb


class LocalLibraryProviderTest(object):
    def setUp(self):
        self.tempdir = tempfile.mkdtemp()
        self.library = zodb.ZodbLibrary(dict(self.config, local={
            'media_dir': self.tempdir,
            'data_dir': self.tempdir,
        }))
        self.library.load()

    def tearDown(self):
        shutil.rmtree(self.tempdir)

    def test_add_noname_ascii(self):
        name = b'Test.mp3'
        uri = translator.path_to_local_track_uri(name)
        track = Track(name=name, uri=uri)
        self.library.begin()
        self.library.add(track)
        self.library.close()
        self.assertEqual([track], self.library.lookup(uri))

    def test_add_noname_utf8(self):
        name = u'Mi\xf0vikudags.mp3'
        uri = translator.path_to_local_track_uri(name.encode('utf-8'))
        track = Track(name=name, uri=uri)
        self.library.begin()
        self.library.add(track)
        self.library.close()
        self.assertEqual([track], self.library.lookup(uri))

    def test_clear(self):
        self.library.begin()
        self.library.add(Track(uri='local:track:track.mp3'))
        self.library.close()
        self.library.clear()
        self.assertEqual(self.library.load(), 0)

    def test_search_artist(self):
        track = Track(
            uri='local:track:track.mp3',
            artists=[Artist(name='Found')])
        self.library.begin()
        self.library.add(track)
        self.assertEqual((track, ),
            self.library.search(query={'artist': ['Found']}).tracks)
        self.assertEqual((),
            self.library.search(query={'artist': ['Not found']}).tracks)

    def test_search_album(self):
        track = Track(
            uri='local:track:track.mp3',
            album=Album(name='Found'))
        self.library.begin()
        self.library.add(track)
        self.assertEqual((track, ),
            self.library.search(query={'album': ['Found']}).tracks)
        self.assertEqual((),
            self.library.search(query={'album': ['Not found']}).tracks)


class LocalLibraryProviderTestWithoutCache(
        LocalLibraryProviderTest,
        unittest.TestCase):

    config = {
        'local-zodb': {
          'cache_mpd': False,
        }
    }

class LocalLibraryProviderTestWithCache(
        LocalLibraryProviderTest,
        unittest.TestCase):

    config = {
        'local-zodb': {
          'cache_mpd': True,
        },
    }

    def _get_context(self):
        # XXX probably not needed, since cache must be filled at this point
        class Context:
            class core:
                class library:
                    @staticmethod
                    def get_distinct(field, query):
                        class FakeDeferredResult:
                            @staticmethod
                            def get():
                                return self.library.get_distinct(field, query)
                        return FakeDeferredResult
        return Context

    def test_mpd_command_list(self):
        from mopidy.mpd.protocol import commands
        track = Track(
            uri='local:track:track.mp3',
            album=Album(name='Found',
                        artists=[Artist(name='Found')]))
        self.library.begin()
        self.library.add(track)
        self.library.flush()

        self.assertEqual(
            1,
            len(commands.handlers['list'](self._get_context(), 'album', 'Found')))
        self.assertEqual(
            0,
            len(commands.handlers['list'](self._get_context(), 'album', 'Not Found')))

        self.assertEqual(
            1,
            len(commands.handlers['list'](self._get_context(), 'album')))
        self.assertEqual(
            1,
            len(commands.handlers['list'](self._get_context(), 'artist')))
