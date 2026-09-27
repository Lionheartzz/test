import {test} from 'node:test';
import assert from 'node:assert/strict';
import {uuidToken,shortToken,randomOwner} from '../web/crypto-utils.js';

test('native and LAN fallback preserve UUID v4 and token formats',()=>{
  const descriptor=Object.getOwnPropertyDescriptor(globalThis,'crypto');
  try{
    Object.defineProperty(globalThis,'crypto',{configurable:true,value:{randomUUID:()=>
      '12345678-1234-4234-8234-123456789abc',getRandomValues:()=>{throw Error('fallback used');}}});
    assert.equal(uuidToken(),'12345678-1234-4234-8234-123456789abc');
    assert.equal(shortToken(),'123456781234');
    Object.defineProperty(globalThis,'crypto',{configurable:true,value:{getRandomValues:bytes=>bytes.fill(0)}});
    assert.match(uuidToken(),/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}$/);
    assert.match(randomOwner(),/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}$/);
    Object.defineProperty(globalThis,'crypto',{configurable:true,value:undefined});
    assert.throws(uuidToken,/Secure random IDs are unavailable/);
  }finally{if(descriptor)Object.defineProperty(globalThis,'crypto',descriptor);else delete globalThis.crypto;}
});
