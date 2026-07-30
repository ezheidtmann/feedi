/*
 * Scroll restoration for the entry list.
 *
 * Opening an article is a regular browser navigation, so going back from one normally
 * hits the browser's back/forward cache: the feed document is resurrected exactly as it
 * was --every infinite scroll page included, at the right scroll offset-- and this
 * script doesn't even run again.
 *
 * When the bfcache misses (the document was evicted, or the feed was reloaded) the
 * browser hands us a fresh feed with a single page of entries, scrolled to the top.
 * What follows rebuilds enough of it to put the reader back where they were: it
 * remembers which entry was at the top of the viewport, re-triggers the infinite scroll
 * until that entry shows up again, and scrolls to it.
 */
(function () {
    "use strict";

    var MAX_AGE_MS = 6 * 60 * 60 * 1000;
    var MAX_PAGE_LOADS = 20;
    var PAGE_LOAD_TIMEOUT_MS = 8000;
    var KEY = "feedi:scroll:" + location.pathname + location.search;

    function readState() {
        try {
            var state = JSON.parse(sessionStorage.getItem(KEY));
            return state && Date.now() - state.ts < MAX_AGE_MS ? state : null;
        } catch (e) {
            return null;
        }
    }

    function isHistoryNavigation() {
        var entries = performance.getEntriesByType && performance.getEntriesByType("navigation");
        if (entries && entries.length) return entries[0].type === "back_forward";
        return performance.navigation && performance.navigation.type === 2;
    }

    function setScrollRestoration(value) {
        if ("scrollRestoration" in history) history.scrollRestoration = value;
    }

    // this runs while the document is still being parsed: if we're going to restore by
    // hand we need to take over now, before the browser scrolls to a position it
    // measured against a feed that had many more entries loaded than it has right now.
    var pending = isHistoryNavigation() ? readState() : null;
    if (pending) setScrollRestoration("manual");

    // htmx used to snapshot whole pages in here for its own history handling. It doesn't
    // anymore (see the htmx-config meta tag), so drop the leftovers: they are megabytes
    // of dead weight against a storage quota that is not generous on phones.
    try {
        localStorage.removeItem("htmx-history-cache");
    } catch (e) {}

    function onReady(fn) {
        if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn);
        else fn();
    }

    onReady(function () {
        var list = document.querySelector("[data-feed-scroll] #main-entry-list");
        if (!list) {
            // not a feed page, hand scrolling back to the browser
            setScrollRestoration("auto");
            return;
        }

        var entries = function () {
            return list.querySelectorAll(".feed-entry");
        };

        function save() {
            var loaded = entries();
            var anchor = null;
            var offset = 0;

            // the topmost entry that is still (even partially) on screen
            for (var i = 0; i < loaded.length; i++) {
                var top = loaded[i].getBoundingClientRect().top;
                if (top + loaded[i].offsetHeight > 0) {
                    anchor = loaded[i].getAttribute("data-id");
                    offset = Math.round(top);
                    break;
                }
            }

            try {
                sessionStorage.setItem(
                    KEY,
                    JSON.stringify({
                        ts: Date.now(),
                        y: Math.round(window.pageYOffset),
                        count: loaded.length,
                        anchor: anchor,
                        offset: offset,
                    })
                );
            } catch (e) {}
        }

        // pagehide covers both leaving for good and being frozen into the bfcache;
        // visibilitychange is the reliable one when the app is backgrounded on mobile.
        window.addEventListener("pagehide", save);
        document.addEventListener("visibilitychange", function () {
            if (document.visibilityState === "hidden") save();
        });

        if (!pending) return;

        function anchorElement() {
            return pending.anchor && list.querySelector('.feed-entry[data-id="' + pending.anchor + '"]');
        }

        function sentinel() {
            return list.querySelector("[hx-get][hx-trigger='revealed']");
        }

        // same request the infinite scroll would make on its own, issued by hand instead
        // of waiting for the sentinel to be revealed
        function loadNextPage() {
            var elt = sentinel();
            if (!elt || !window.htmx) return Promise.resolve(false);

            var swap = window.htmx.ajax("GET", elt.getAttribute("hx-get"), {
                source: elt,
                target: elt,
                swap: "outerHTML",
            });
            if (!swap || !swap.then) return Promise.resolve(false);

            var request = swap.then(
                function () {
                    return true;
                },
                function () {
                    return false;
                }
            );
            var timeout = new Promise(function (resolve) {
                setTimeout(function () {
                    resolve(false);
                }, PAGE_LOAD_TIMEOUT_MS);
            });

            return Promise.race([request, timeout]);
        }

        function settle(target) {
            var stopped = false;
            var timers = [];

            function stop() {
                if (stopped) return;
                stopped = true;
                timers.forEach(clearTimeout);
                setScrollRestoration("auto");
            }

            function apply() {
                if (stopped) return;
                window.scrollTo(0, Math.max(0, Math.round(target())));
            }

            // images and web fonts land late on a phone and shift everything below them,
            // so keep correcting for a moment -- unless the reader is already scrolling,
            // in which case yanking them around would be worse than being slightly off.
            ["touchstart", "wheel", "keydown"].forEach(function (event) {
                window.addEventListener(event, stop, { once: true, passive: true });
            });
            [0, 60, 150, 400, 800].forEach(function (delay) {
                timers.push(setTimeout(apply, delay));
            });
            timers.push(setTimeout(stop, 1200));
        }

        (async function restore() {
            var anchor = anchorElement();
            var loads = 0;

            while (!anchor && loads < MAX_PAGE_LOADS && entries().length < pending.count && sentinel()) {
                // follow the feed down as it grows: reads as a quick catch up scroll
                // instead of a page that appears stuck at the top
                window.scrollTo(0, pending.y);
                if (!(await loadNextPage())) break;
                loads++;
                anchor = anchorElement();
            }

            settle(
                anchor
                    ? function () {
                          return anchor.getBoundingClientRect().top + window.pageYOffset - pending.offset;
                      }
                    : function () {
                          return pending.y;
                      }
            );
        })();
    });
})();
