import gzip
import json

import tornado
import tornado.web
import tornado.httpserver
import tornado.httputil
import tornado.iostream
from os.path import isfile
from tornado import escape
from tornado.escape import utf8
from datetime import date, timedelta
from dateutil import parser


class BaseHandler(tornado.web.RequestHandler):
    callback = None

    def initialize(self):
        self.callback = self.get_argument('callback', default=None)

    def sendResponse(self, data):
        if isinstance(data, dict) or isinstance(data, list):
            data = escape.json_encode(data)
            self.set_header('Content-Type', 'application/json; charset=UTF-8')

        if self.callback:
            self.set_header('Content-Type', 'application/javascript; charset=UTF-8')
            self._write_buffer.append(utf8('%s(%s)' % (self.callback, data)))
        else:
            self._write_buffer.append(utf8(data))
        self.finish()

    def write_error(self, status_code, **kwargs):
        http_explanations = {
            400: 'Request not properly formatted or contains languages that Apertium APy does not support',
            404: 'Resource requested does not exist. URL may have been mistyped',
            408: 'Server did not receive a complete request within the time it was prepared to wait. Try again',
            500: 'Unexpected condition on server. Request could not be fulfilled.'
        }
        explanation = kwargs.get('explanation', http_explanations.get(status_code, ''))
        if 'exc_info' in kwargs and len(kwargs['exc_info']) > 1:
            exception = kwargs['exc_info'][1]
            if hasattr(exception, 'log_message') and exception.log_message:
                explanation = exception.log_message % exception.args
            elif hasattr(exception, 'reason'):
                explanation = exception.reason or tornado.httputil.responses.get(status_code, 'Unknown')
            else:
                explanation = tornado.httputil.responses.get(status_code, 'Unknown')

        result = {
            'status': 'error',
            'code': status_code,
            'message': tornado.httputil.responses.get(status_code, 'Unknown'),
            'explanation': explanation
        }

        data = escape.json_encode(result)
        self.set_header('Content-Type', 'application/json; charset=UTF-8')

        if self.callback:
            self.set_header('Content-Type', 'application/javascript; charset=UTF-8')
            self._write_buffer.append(utf8('%s(%s)' % (self.callback, data)))
        else:
            self._write_buffer.append(utf8(data))
        self.finish()

    def set_default_headers(self):
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.set_header('Access-Control-Allow-Headers',
                        'accept, cache-control, origin, x-requested-with, x-file-name, content-type')

class StatsHandler(BaseHandler):

    def get_date(self):

        yesterday = date.today() - timedelta(days=1)

        sdt = self.get_query_argument('date', yesterday.isoformat())

        try:

            dt = parser.parse(sdt).date()
            dtlog = dt + timedelta(days=1)
            return dt.isoformat(), dtlog.isoformat()
        except:
            raise Exception("date provided ({0}) is not properly formatted".format(sdt))


    @tornado.web.asynchronous
    def get(self):

        try:
            dt, log_date = self.get_date()

            f = self.get_file_content(log_date)

        except Exception as e:
            self.write_error(500, explanation=str(e))
            return

        self.sendResponse({
            'date'  : dt,
            'status': 200,
            'result': f
        })

    def get_file_content(self, dt):
        path, gz = self.get_path(dt)
        if isfile(path):
            stats = ApertiumStats()
            if gz:
                content = gzip.open(path, 'rt')
            else:
                content = open(path)
            for line in content.readlines():
                elems = line.split(' ')
                stats.inc()
                stats.add_pair(elems[2])
                stats.add_source(elems[4], elems[6])
            return stats
        else:
            return False

    def get_path(self, dt):
        path = "/var/log/traductor/ScaleMTRequests.log.{0}".format(dt)
        if isfile(path):
            return path, False

        y = dt.split('-')[0]
        path = "/opt/traductor-requests/{0}/ScaleMTRequests.log.{1}.gz".format(y,dt)
        if isfile(path):
            return path, True

        return False, False


class ApertiumStats(dict):

    langs = {
        'en' : 'eng',
        'eng': 'eng',
        'ca' : 'cat',
        'cat': 'cat',
        'ca_valencia' : 'cat_valencia',
        'cat_valencia': 'cat_valencia',
        'spa': 'spa',
        'es' : 'spa',
        'fr' : 'fra',
        'fra': 'fra',
        'pt' : 'por',
        'por': 'por',
        'it' : 'ita',
        'ita': 'ita',
        'oc' : 'oci',
        'oci': 'oci',
        'oc_aran' : 'oci_aran',
        'oci_aran': 'oci_aran',

    }

    def __init__(self):
        self['total'] = 0
        self['langstats'] = {}
        self['srcstats'] = {}

    def inc(self):
        self['total'] += 1

    def add_pair(self, pair):
        if pair == '':
            key = 'unknown'
        else:
            left, right = pair.split('|')
            sleft = self.langs.get(left, left)
            sright = self.langs.get(right, right)
            key = sleft+'-'+sright

        if key == '-':
            key = 'unknown'

        self['langstats'].setdefault(key, 0)
        self['langstats'][key] += 1

    def add_source(self, key, referer):
        if key in ['traductor@softcatala.org', 'traductor@softvalencia.org']:
            if "softvalencia" in referer:
                key = 'traductor@softvalencia.org'
            else:
                key = 'traductor@softcatala.org'

        self['srcstats'].setdefault(key, 0)
        self['srcstats'][key] += 1


if __name__ == '__main__':
    application = tornado.web.Application([
        (r'/', StatsHandler)
    ])

    http_server = tornado.httpserver.HTTPServer(application)

    http_server.bind(7890)
    http_server.start()

    loop = tornado.ioloop.IOLoop.instance()

    loop.start()

