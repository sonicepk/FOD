from gevent import monkey
monkey.patch_all()
from gevent.pool import Pool
import json

import uuid
import simplejson
import datetime
from django.shortcuts import render_to_response
from django.template.loader import render_to_string
from django.http import HttpResponse
from gevent.event import Event
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse


from flowspy.utils import beanstalkc

import logging

FORMAT = '%(asctime)s %(levelname)s: %(message)s'
logging.basicConfig(format=FORMAT)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def create_message(body, user):
    data = {'id': str(uuid.uuid4()), 'body': body, 'user':user}
    data['html'] = render_to_string('poll_message.html', dictionary={'message': data})
    return data


def json_response(value, **kwargs):
    kwargs.setdefault('content_type', 'text/javascript; charset=UTF-8')
    return HttpResponse(simplejson.dumps(value), **kwargs)

class Msgs(object):
    cache_size = 200

    def __init__(self):
        self.user = None
        self.user_cache = {}
        self.user_cursor = {}
        self.cache = []
        self.new_message_event = None
        self.new_message_user_event = {}

    def main(self, request):
        if self.user_cache:
            request.session['cursor'] = self.user_cache[-1]['id']
        return render_to_response('poll.html', {'messages': self.user_cache})

    @csrf_exempt
    def message_existing(self, request):
        if request.is_ajax():
            try:
                user = request.user.get_profile().peer.domain_name
            except:
                user = None
                return False
            try:
                assert(self.new_message_user_event[user])
            except:
                self.new_message_user_event[user] = Event()
    #        self.new_message_user_event[user] = Event()
            try:
                if self.user_cache[user]:
                    self.user_cursor[user] = self.user_cache[user][-1]['id']
            except:
                self.user_cache[user] = []
                self.user_cursor[user] = ''
            return json_response({'messages': self.user_cache[user]})
        return HttpResponseRedirect(reverse('login'))
    
    @csrf_exempt
    def message_new(self, mesg=None):
        if mesg:
            message = mesg['message']
            user = mesg['username']
            now = datetime.datetime.now()
            msg = create_message("[%s]: %s"%(now.strftime("%Y-%m-%d %H:%M:%S"),message), user)
        try:
            isinstance(self.user_cache[user], list)
        except:
            self.user_cache[user] = []
        self.user_cache[user].append(msg)
        if self.user_cache[user][-1] == self.user_cache[user][0]: 
            self.user_cursor[user] = self.user_cache[user][-1]['id']
        else:
            self.user_cursor[user] = self.user_cache[user][-2]['id']
#        self.cache.append(msg)
        if len(self.user_cache[user]) > self.cache_size:
            self.user_cache[user] = self.user_cache[user][-self.cache_size:]
        self.new_message_user_event[user].set()
        self.new_message_user_event[user].clear()
        return json_response(msg)
    
    @csrf_exempt
    def message_updates(self, request):
        if request.is_ajax():
            cursor = {}
            try:
    #            user = request.user.username
                user = request.user.get_profile().peer.domain_name
            except:
                user = None
                return False
            cursor[user] = self.user_cursor[user]
                
            try:
                if not isinstance(self.user_cache[user], list):
                    self.user_cache[user] = []
            except:
                self.user_cache[user] = []
            if not self.user_cache[user] or cursor[user] == self.user_cache[user][-1]['id']:
                self.new_message_user_event[user].wait()
    #            self.new_message_event.wait()
    #        assert cursor[user] != self.user_cache[user][-1]['id'], cursor[user]
            try:
                for index, m in enumerate(self.user_cache[user]):
                    if m['id'] == cursor[user]:
                        return json_response({'messages': self.user_cache[user][index + 1:]})
                return json_response({'messages': self.user_cache[user]})
            finally:
                if self.user_cache[user]:
                    self.user_cursor[user] = self.user_cache[user][-1]['id']
        return HttpResponseRedirect(reverse('login'))
    #            else:
    #                request.session.pop('cursor', None)

    def monitor_polls(self, polls=None):
        b = beanstalkc.Connection()
        b.watch(settings.POLLS_TUBE)
        while True:
            job = b.reserve()
            msg = json.loads(job.body)
            job.bury()
            self.message_new(msg)
            
    
    def start_polling(self):
        logger.info("Start Polling")
        p = Pool(10)
        while True:
            p.spawn(self.monitor_polls)
            
msgs = Msgs()

main = msgs.main

message_new = msgs.message_new
message_updates = msgs.message_updates
message_existing = msgs.message_existing

poll = msgs.start_polling
poll()









