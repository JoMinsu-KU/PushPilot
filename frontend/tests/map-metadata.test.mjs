import assert from 'node:assert/strict';
import test from 'node:test';
import { nodeLabel, destinationOptions, destinationPage, destinationGoal } from '../src/mapMetadata.ts';

const map = {
  id: 'replacement-map', title: 'Harbor District', start: 'DEPOT',
  destinations: ['PORT', 'LIBRARY', 'PARK', 'STATION'],
  nodes: [{id:'DEPOT',label:'South Depot'}, {id:'PORT',label:'Harbor'}, {id:'LIBRARY',label:'Library'}, {id:'PARK',label:'Harbor'}, {id:'STATION'}],
};

test('replacement-map titles and destination labels preserve independent node identities', () => {
  assert.equal(nodeLabel(map, map.start), 'South Depot');
  assert.equal(nodeLabel(map, 'STATION'), 'STATION');
  assert.equal(nodeLabel(null, 'PORT'), 'PORT');
  assert.equal(nodeLabel(map, null), '—');
  assert.deepEqual(destinationOptions(map).map(item=>item.id), map.destinations);
  assert.equal(destinationOptions(map)[0].label, destinationOptions(map)[2].label);
  assert.equal(destinationGoal(map, 'PARK'), 'Push the car from DEPOT to PARK.');
});

test('additional destinations stay accessible through bounded pages after map replacement', () => {
  const options = destinationOptions(map);
  assert.deepEqual(destinationPage(options, 0).items.map(item=>item.id), ['PORT','LIBRARY','PARK']);
  assert.deepEqual(destinationPage(options, 1).items.map(item=>item.id), ['STATION']);
  assert.equal(destinationPage(options, 99).page, 1);
  assert.deepEqual(destinationPage([], 5), {items:[],page:0,pages:1});
});
