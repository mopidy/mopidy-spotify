from __future__ import unicode_literals

import os

# TODO: Comment in if you need to register GStreamer elements below, else
# remove entirely
#import pygst
#pygst.require('0.10')
#import gst
#import gobject

from mopidy import config, ext


__version__ = '0.1.0'


class Extension(ext.Extension):

    dist_name = 'Mopidy-Spotify'
    ext_name = 'spotify'
    version = __version__

    def get_default_config(self):
        conf_file = os.path.join(os.path.dirname(__file__), 'ext.conf')
        return config.read(conf_file)

    def get_config_schema(self):
        schema = super(Extension, self).get_config_schema()
        # TODO: Comment in and edit, or remove entirely
        #schema['username'] = config.String()
        #schema['password'] = config.Secret()
        return schema

    # You will typically only implement one of the next three methods
    # in a single extension.

    # TODO: Comment in and edit, or remove entirely
    #def get_frontend_classes(self):
    #    from .frontend import FoobarFrontend
    #    return [FoobarFrontend]

    # TODO: Comment in and edit, or remove entirely
    #def get_backend_classes(self):
    #    from .backend import FoobarBackend
    #    return [FoobarBackend]

    # TODO: Comment in and edit, or remove entirely
    #def register_gstreamer_elements(self):
    #    from .mixer import FoobarMixer
    #    gobject.type_register(FoobarMixer)
    #    gst.element_register(
    #        FoobarMixer, 'foobarmixer', gst.RANK_MARGINAL)
