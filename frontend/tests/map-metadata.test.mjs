import assert from 'node:assert/strict';
import test from 'node:test';
import { nodeLabel, planStepLabel, destinationOptions, destinationPage, destinationGoal } from '../src/mapMetadata.ts';

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

test('Pizza shop is a display alias without changing map, goal or destination identifiers', () => {
  const city = { ...map, start: 'PIZZA', nodes: [{ id: 'PIZZA', label: 'Pizza' }, ...map.nodes] };
  const before = JSON.stringify(city);
  assert.equal(nodeLabel(city, 'PIZZA'), 'Pizza shop');
  assert.equal(nodeLabel(null, 'PIZZA'), 'Pizza shop');
  assert.equal(planStepLabel(city, { label: 'Leave PIZZA', node_id: 'PIZZA' }), 'Leave Pizza shop');
  assert.equal(destinationGoal(city, 'PORT'), 'Push the car from PIZZA to PORT.');
  assert.equal(JSON.stringify(city), before);
  assert.equal(nodeLabel({ ...city, nodes: [{ id: 'PIZZA', label: 'New restaurant' }] }, 'PIZZA'), 'New restaurant');
  assert.equal(nodeLabel({ ...city, nodes: [{ id: 'OTHER', label: 'Pizza' }] }, 'OTHER'), 'Pizza');
});
