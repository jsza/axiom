# -*- test-case-name: axiom.test.test_scheduler -*-
from twisted.internet import reactor

from twisted.application.service import Service, IService
from twisted.python import log

from epsilon.extime import Time

from axiom.item import Item
from axiom.attributes import timestamp, reference, text, integer, inmemory
from axiom.slotmachine import Attribute
from axiom.iaxiom import IScheduler

class TimedEvent(Item):
    typeName = 'timed_event'
    schemaVersion = 1

    time = timestamp(indexed=True)
    runnable = reference()

class Scheduler(Item, Service):

    typeName = 'scheduler'
    schemaVersion = 1

    parent = inmemory()
    running = inmemory()
    name = inmemory()
    timer = inmemory()

    eventsRun = integer()
    lastEventAt = timestamp()
    nextEventAt = timestamp()

    def activate(self):
        self.timer = None
        self.running = False

    def __init__(self, **kw):
        super(Scheduler, self).__init__(**kw)
        self.eventsRun = 0
        self.lastEventAt = None
        self.nextEventAt = None

    def installOn(self, other):
        other.powerUp(self, IService)
        other.powerUp(self, IScheduler)

    def now(self):
        # testing hook
        return Time()

    def callLater(self, s, f, *a, **k):
        s = max(s, 0.00000001)
        return reactor.callLater(s, f, *a, **k)

    def tick(self):
        now = self.now()
        any = 0
        self.timer = None
        self.nextEventAt = None
        before = self.eventsRun
        for event in self.store.query(TimedEvent,
                                      TimedEvent.time < now,
                                      sort=TimedEvent.time.ascending):
            self.eventsRun += 1
            newTime = event.runnable.run()
            if newTime is not None:
                event.time = newTime
            else:
                event.deleteFromStore()
                # XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX omfg what
                event.checkpoint()
            any = 1
        if any:
            self.lastEventAt = now
        x = list(
            self.store.query(TimedEvent, sort=TimedEvent.time.ascending, limit=1))
        if x:
            if self.timer is not None:
                self.timer.cancel()
            x = x[0]
            self.timer = self.callLater(
                x.time.asPOSIXTimestamp() - now.asPOSIXTimestamp(),
                self.store.transact, self.tick)
            self.nextEventAt = x.time
        log.msg("%d events run" % (self.eventsRun - before,))


    def schedule(self, runnable, when):
        TimedEvent(store=self.store, time=when, runnable=runnable)
        if self.running:
            if self.timer is None:
                self.timer = self.callLater(0.00001, self.store.transact, self.tick)

    def startService(self):
        super(Scheduler, self).startService()
        self.store.transact(self.tick)

    def stopService(self):
        super(Scheduler, self).stopService()
        if hasattr(self, 'timer'):
            self.timer.cancel()
            self.timer = None
