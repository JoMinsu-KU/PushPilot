import assert from 'node:assert/strict';
import test from 'node:test';
import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { acceptDisplayCursor, advanceDisplayFeed, displayFeedFresh, directionLegs, displayMatchesStatus, displaySignalLabel, parsePhysicalDisplay, physicalCarTrack, updatePhysicalCarMotion } from '../src/physicalDisplay.ts';
import { portableSha256 } from '../src/assetIntegrity.ts';
import { cityDisplayFit, cityPreviewWorld } from '../src/cityRoutePreview.ts';

const hash = '9fea848ee172ea6779edda861ddb15c51ba562117d77a3558eb8a85811aefb50';
const status = { mission_id:'mission-a', plan_id:'plan-a', plan_revision:3, workspace_session_id:'session-a', state:'RUNNING',
  signal:{color:'GREEN',waiting:false,stable_green_frames:0,required_green_frames:2} };
const snapshot = () => ({ schema_version:'pushpilot.physical-display.v1',producer_epoch:'a'.repeat(32),available:true,reason:null,sequence:10,
  captured_at:'2026-10-30T12:00:00Z',mission_id:'mission-a',plan_id:'plan-a',plan_revision:3,workspace_session_id:'session-a',map_hash:hash,
  state:'RUNNING',phase:'contact',primitive_id:'C/contact',stage_id:'contact-1',stage_index:0,stage_count:5,stage_status:'confirmed',
  animation_authority:'confirmed_only',motion_authority:false,
  vehicle:{estimated:true,route_fraction:.25,route_leg_index:0,leg_fraction:.5,confirmed_contact_stages:1,total_contact_stages:5,heading:'EAST',moving:true,last_confirmed_at:'2026-10-30T12:00:00Z'},
  signal:{phase:'passed',green_count:0,green_required:2} });
const map = {geometry_hash:hash};
const display = {points:[[10,100],[60,100],[110,100],[110,50],[110,10],[30,10]]};

test('confirmed contact progress follows semantic EAST/NORTH/WEST legs, never tool coordinates',()=>{
  const source=snapshot(), first=physicalCarTrack(map,display,source);
  assert.deepEqual(first.path,[[10,100],[110,100],[110,10],[30,10]]); assert.equal(first.distance_mm,50);
  source.vehicle.route_leg_index=1; source.vehicle.leg_fraction=.25;
  assert.equal(physicalCarTrack(map,display,source).distance_mm,122.5);
  source.vehicle.route_leg_index=2; source.vehicle.leg_fraction=.5;
  assert.equal(physicalCarTrack(map,display,source).distance_mm,230);
  assert.deepEqual(directionLegs([[0,0],[1,0],[2,0]]),[[0,0],[2,0]]);
});
test('approach, withdrawal, wrist, wait, review, recontact, return and HOLD cannot animate a vehicle',()=>{
  for (const phase of ['approach','withdraw','wrist','recontact','signal_wait','muse_review','return','hold','complete']) {
    const source=snapshot(); source.phase=phase;
    assert.equal(physicalCarTrack(map,display,source).animate,false,phase);
  }
  for (const patch of [{stage_status:'intent'},{feed_fresh:false},{state:'HOLD'}]) assert.equal(physicalCarTrack(map,display,{...snapshot(),...patch}).animate,false);
});
test('stale or repeated receipts freeze; restart or new mission places without replaying the old route',()=>{
  const track=physicalCarTrack(map,display,snapshot());
  const options={animate:true,fresh:true,reduced:false};
  const current={key:track.key,distance:20,tween:null};
  const next=updatePhysicalCarMotion(current,track,100,options);
  assert.deepEqual(next.tween,{from:20,to:50,start:100,duration:650});
  assert.deepEqual(updatePhysicalCarMotion(next,track,200,options),next);
  assert.deepEqual(updatePhysicalCarMotion({...next,distance:25},track,300,{...options,fresh:false}),{key:track.key,distance:25,tween:null});
  assert.equal(updatePhysicalCarMotion(current,{...track,key:'new-mission'},200,options).tween,null);
  assert.equal(updatePhysicalCarMotion({...current,distance:60},track,200,options).distance,60);
  assert.equal(updatePhysicalCarMotion(current,{...track,animate:false},200,options).tween,null);
});
test('unknown/incorrect map or malformed feed cannot invent a vehicle pose',()=>{
  assert.equal(physicalCarTrack({...map,geometry_hash:'changed'},display,snapshot()),null);
  assert.equal(physicalCarTrack(map,display,{...snapshot(),available:false}),null);
  assert.equal(physicalCarTrack(map,display,{...snapshot(),vehicle:{...snapshot().vehicle,route_leg_index:99}}),null);
  assert.throws(()=>parsePhysicalDisplay({...snapshot(),motion_authority:true}));
  assert.throws(()=>parsePhysicalDisplay({...snapshot(),producer_epoch:undefined}));
  assert.throws(()=>parsePhysicalDisplay({...snapshot(),vehicle:{...snapshot().vehicle,leg_fraction:NaN}}));
  assert.equal(parsePhysicalDisplay(snapshot()).motion_authority,false);
  assert.equal(displayMatchesStatus({...snapshot(),plan_id:'old-plan'},status),false);
  assert.equal(displayMatchesStatus({...snapshot(),workspace_session_id:'old-session'},status),false);
});
test('producer sequence ordering survives service restart and refuses retired producers',()=>{
  let cursor=acceptDisplayCursor({producer:null,sequence:-1,retired:[]},snapshot(),status);
  assert.throws(()=>acceptDisplayCursor(cursor,{...snapshot(),sequence:9},status));
  cursor=acceptDisplayCursor(cursor,{...snapshot(),producer_epoch:'b'.repeat(32),sequence:0},status);
  assert.equal(cursor.sequence,0); assert.deepEqual(cursor.retired,['a'.repeat(32)]);
  assert.throws(()=>acceptDisplayCursor(cursor,{...snapshot(),sequence:50},status));
  assert.throws(()=>acceptDisplayCursor(cursor,{...snapshot(),mission_id:'old'},status));
});
test('cached successful GET responses cannot extend a stopped collector moving indication',()=>{
  let feed={cursor:{producer:null,sequence:-1,retired:[]},advanced_at:null};
  assert.equal(displayFeedFresh(feed,0),false);
  feed=advanceDisplayFeed(feed,snapshot(),status,100);
  assert.equal(displayFeedFresh(feed,100),true);
  for (const now of [1000,2000,3000,4000,5000]) feed=advanceDisplayFeed(feed,snapshot(),status,now);
  assert.equal(feed.advanced_at,100); assert.equal(displayFeedFresh(feed,5000),false);
  const frozen=physicalCarTrack(map,display,{...snapshot(),feed_fresh:displayFeedFresh(feed,5000)});
  assert.equal(frozen.animate,false);
  feed=advanceDisplayFeed(feed,{...snapshot(),sequence:11},status,5100);
  assert.equal(feed.advanced_at,5100); assert.equal(displayFeedFresh(feed,5100),true);
  feed=advanceDisplayFeed(feed,{...snapshot(),producer_epoch:'b'.repeat(32),sequence:0},status,9000);
  assert.equal(feed.advanced_at,9000); assert.equal(displayFeedFresh(feed,9000),true);
  assert.throws(()=>advanceDisplayFeed(feed,snapshot(),status,9100));
});
test('passed signal stays passed when the executor resets its accepted green frame counter',()=>{
  assert.equal(displaySignalLabel(status,true,snapshot()),'Signal passed');
  assert.notEqual(displaySignalLabel(status,true,{...snapshot(),mission_id:'old'}),'Signal passed');
  assert.equal(displaySignalLabel(status,false,snapshot()),'Status unavailable');
});
test('new artwork correspondence is independently hash-bound and leaves physical map metadata unchanged',async()=>{
  const manifest=JSON.parse(await readFile(new URL('../public/models/city-display.json',import.meta.url),'utf8'));
  const source={...map,board:{width_mm:420,height_mm:297},nodes:[{x_mm:100,y_mm:100},{x_mm:200,y_mm:200}],spatial_preview:{old:'unchanged'}};
  const original=JSON.stringify(source), fit=cityDisplayFit(source,manifest,manifest.model.sha256);
  assert.ok(fit); assert.equal(JSON.stringify(source),original);
  assert.equal(cityDisplayFit(source,manifest,'f'.repeat(64)),null);
  assert.equal(cityDisplayFit({...source,geometry_hash:'changed'},manifest,manifest.model.sha256),null);
  assert.deepEqual(cityPreviewWorld([fit.left,fit.top],fit),[-241,.6,-154]);
});
test('SHA-256 verification works on LAN HTTP without WebCrypto',async()=>{
  for(const text of ['', 'abc', 'a'.repeat(64), 'a'.repeat(1000000)]) {
    const data=new TextEncoder().encode(text);
    assert.equal(await portableSha256(data.buffer),createHash('sha256').update(data).digest('hex'));
  }
});
