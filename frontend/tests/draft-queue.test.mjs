import assert from 'node:assert/strict';
import test from 'node:test';
import { DraftQueue } from '../src/draft-queue.ts';

function message(body, version = 1, ticketVersion = 1) {
  return { id: 'reply-1', body, version, ticket_version: ticketVersion };
}

test('typing during a save is preserved and serialized against the returned version', async () => {
  const firstWrite = Promise.withResolvers();
  const writes = [];
  const queue = new DraftQueue(null, async (body, saved) => {
    writes.push({ body, version: saved?.version ?? null });
    if (writes.length === 1) await firstWrite.promise;
    return message(body, (saved?.version ?? 0) + 1);
  }, () => {});
  queue.edit('First draft ');
  const flight = queue.flush();
  await Promise.resolve();
  queue.edit('Newer text typed during the request ');
  assert.equal(queue.flush(), flight);
  firstWrite.resolve();
  await flight;
  assert.deepEqual(writes, [{ body: 'First draft', version: null }, { body: 'Newer text typed during the request', version: 1 }]);
  assert.equal(queue.snapshot().body, 'Newer text typed during the request ');
  assert.equal(queue.snapshot().saved.version, 2);
  assert.equal(queue.snapshot().dirty, false);
  assert.equal(queue.snapshot().saving, false);
});

test('a failed write preserves text and cannot overwrite a newer server version silently', async () => {
  const conflict = new Error('A newer draft exists');
  const queue = new DraftQueue(message('Original'), async () => { throw conflict; }, () => {});
  queue.edit('My unsaved reply');
  await assert.rejects(queue.flush(), conflict);
  queue.observe(message('Another agent edited this', 2));
  assert.equal(queue.snapshot().body, 'My unsaved reply');
  assert.equal(queue.snapshot().saved.version, 1);
  await assert.rejects(queue.flush());
  queue.discard(message('Another agent edited this', 2));
  queue.persist = async (body, saved) => message(body, saved.version + 1);
  queue.edit('Reviewed against the newer draft');
  await queue.flush();
  assert.equal(queue.snapshot().saved.version, 3);
  assert.equal(queue.snapshot().saved.body, 'Reviewed against the newer draft');
});

test('an empty reply failure releases the flight so an explicit retry can succeed', async () => {
  const queue = new DraftQueue(message('Original'), async (body, saved) => message(body, saved.version + 1), () => {});
  queue.edit('   ');
  await assert.rejects(queue.flush(), /empty/);
  assert.equal(queue.snapshot().saving, false);
  queue.edit('Restored reply');
  await queue.flush({ retry: true });
  assert.equal(queue.snapshot().saved.body, 'Restored reply');
  assert.equal(queue.snapshot().saved.version, 2);
});

test('a clean draft acknowledges changed conversation context only after an explicit save', async () => {
  let writes = 0;
  const queue = new DraftQueue(message('Unchanged reply'), async (body, saved) => {
    writes++;
    return message(body, saved.version + 1, 2);
  }, () => {});
  await queue.flush();
  assert.equal(writes, 0);
  assert.equal(queue.snapshot().saved.ticket_version, 1);
  await queue.flush({ force: true });
  assert.equal(writes, 1);
  assert.equal(queue.snapshot().saved.ticket_version, 2);
});

test('a draft approved elsewhere can be recovered as new without editing approved content', async () => {
  const queue = new DraftQueue(message('Previously saved'), async (body, saved) => {
    assert.equal(saved, null);
    return { ...message(body), id: 'reply-2' };
  }, () => {});
  queue.edit('My unsaved addition');
  queue.observe(null);
  assert.ok(queue.snapshot().error);
  queue.startNew();
  await queue.flush();
  assert.equal(queue.snapshot().saved.id, 'reply-2');
  assert.equal(queue.snapshot().body, 'My unsaved addition');
});
