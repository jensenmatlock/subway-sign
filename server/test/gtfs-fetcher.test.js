import { test } from 'node:test';
import assert from 'node:assert/strict';
import GtfsRealtimeBindings from 'gtfs-realtime-bindings';
import { fetchAllFeeds } from '../lib/gtfs-fetcher.js';

const { FeedMessage } = GtfsRealtimeBindings.transit_realtime;

// A minimal valid GTFS-RT feed, run through the real encode path so fetchFeed's
// decode exercises the production code.
function encodedFeed() {
  const msg = FeedMessage.create({ header: { gtfsRealtimeVersion: '2.0' } });
  return FeedMessage.encode(msg).finish();
}

function okResponse(bytes) {
  // protobufjs finish() can return a view into a pooled buffer, so copy out the
  // exact range into its own ArrayBuffer (what a real Response.arrayBuffer gives).
  const ab = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  return { ok: true, arrayBuffer: async () => ab };
}

test('serves the last good feed when a later fetch fails', async (t) => {
  const realFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = realFetch; });

  let call = 0;
  globalThis.fetch = async () => {
    call += 1;
    if (call === 1) return okResponse(encodedFeed());
    throw new Error('simulated timeout');
  };

  const first = await fetchAllFeeds({ lastgood: 'http://feed' });
  assert.ok(first.lastgood, 'first fetch should decode a feed');

  const second = await fetchAllFeeds({ lastgood: 'http://feed' });
  // Same decoded object is reused rather than collapsing to null.
  assert.equal(second.lastgood, first.lastgood);
});

test('returns null when a feed has never succeeded', async (t) => {
  const realFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = realFetch; });

  globalThis.fetch = async () => { throw new Error('down'); };

  const result = await fetchAllFeeds({ neverok: 'http://feed' });
  assert.equal(result.neverok, null);
});
