*****************
Mopidy-Local-ZODB
*****************

ZODB local library extension.

.. image:: https://travis-ci.org/perrinjerome/mopidy-local-zodb.svg
    :target: https://travis-ci.org/perrinjerome/mopidy-local-zodb

Installation
============

Install by running::

    pip install Mopidy-Local-ZODB

Configuration
=============

Before starting Mopidy, you must change your configuration to switch to using
Mopidy-Local-ZODB as your preferred local library::

    [local]
    library = zodb

Once this has been set you can re-scan your library to populate ZODB::

    mopidy local scan


Mopidy-Local-ZODB also features a cache of some list and search MPD queries
that is filled during scan. This has been tested mostly with MPDroid client.

The cache can be disabled with this configuration::

    [local-zodb]
    cache_mpd = false

