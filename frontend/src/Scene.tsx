import { Icon } from './Icons';
import type { MissionState } from '../../contracts/workspace';

export function Scene({ state }: { state: MissionState }) {
  return <div className="scene-art">
    <svg className="tabletop-scene" viewBox="0 0 1000 620" role="img" aria-labelledby="scene-title scene-description">
      <title id="scene-title">Illustrative PushPilot tabletop workspace</title>
      <desc id="scene-description">An original illustration of a robot beside a wheel-less white car on an unregistered tabletop. A symbolic Bakery destination is shown. No measured route or live camera feed is displayed.</desc>
      <defs>
        <linearGradient id="scene-bg" x2="1" y2="1"><stop stopColor="#173146"/><stop offset=".55" stopColor="#091b2a"/><stop offset="1" stopColor="#07111e"/></linearGradient>
        <linearGradient id="table" x2="0.6" y2="1"><stop stopColor="#466074"/><stop offset="1" stopColor="#182f43"/></linearGradient>
        <linearGradient id="board" x2="1" y2="1"><stop stopColor="#c3d1d7"/><stop offset=".5" stopColor="#93abb8"/><stop offset="1" stopColor="#6b889c"/></linearGradient>
        <linearGradient id="metal" x2="1" y2=".5"><stop stopColor="#12283a"/><stop offset=".38" stopColor="#8095a3"/><stop offset=".58" stopColor="#d0d9df"/><stop offset=".75" stopColor="#344d62"/><stop offset="1" stopColor="#0a1c2e"/></linearGradient>
        <linearGradient id="orange" x2="1" y2="1"><stop stopColor="#ffb45d"/><stop offset=".45" stopColor="#fb7c26"/><stop offset="1" stopColor="#b43a12"/></linearGradient>
        <linearGradient id="car-top" x2=".4" y2="1"><stop stopColor="#fff"/><stop offset="1" stopColor="#afc1cf"/></linearGradient>
        <linearGradient id="car-side" x2="1" y2="1"><stop stopColor="#8a9eaf"/><stop offset="1" stopColor="#d1dfe7"/></linearGradient>
        <radialGradient id="pool"><stop stopColor="#0ba6fa" stopOpacity=".2"/><stop offset="1" stopColor="#0ba6fa" stopOpacity="0"/></radialGradient>
        <filter id="shadow" x="-40%" y="-40%" width="200%" height="220%"><feGaussianBlur stdDeviation="12"/></filter>
        <filter id="glow"><feGaussianBlur stdDeviation="3"/></filter>
        <pattern id="workshop" width="160" height="140" patternUnits="userSpaceOnUse"><path d="M0 139h160M159 0v140" stroke="#92b6c8" strokeOpacity=".06" strokeWidth="2"/></pattern>
      </defs>
      <rect width="1000" height="620" fill="url(#scene-bg)"/>
      <rect width="1000" height="620" fill="url(#workshop)"/>
      <path d="M800 0v236m20-236v234M0 174h1000" stroke="#83afc2" strokeWidth="5" opacity=".08"/>
      <ellipse cx="580" cy="410" rx="475" ry="240" fill="url(#pool)"/>
      <path d="m128 254 585-108 321 309-720 159L90 393Z" fill="#010911" opacity=".5" filter="url(#shadow)"/>
      <path d="m124 240 586-94 322 300-728 168L85 378Z" fill="url(#table)" stroke="#54788f" strokeWidth="2"/>
      <path d="m124 240-39 138 219 236v-17L104 375l36-120Z" fill="#10293d"/>
      <path d="m304 597 728-168v17L304 614Z" fill="#0b2438"/>
      <path d="m235 278 430-79 252 224-518 123-216-201Z" fill="#020a14" opacity=".45" filter="url(#shadow)"/>
      <path d="m233 259 431-76 252 232-518 120-216-203Z" fill="url(#board)" stroke="#cae0eb" strokeWidth="2"/>
      <path d="m233 259 431-76 252 232-518 120-216-203Z" fill="none" stroke="#05c5ff" strokeOpacity=".18" strokeWidth="6"/>
      <path d="m245 268 414-73 242 220-503 106-203-189Z" fill="none" stroke="#edfaff" strokeOpacity=".2"/>
      <g opacity=".45" fill="#102638"><path d="m239 275 28-5 15 14-29 6Z"/><path d="m650 200 28-5 15 14-29 6Z"/><path d="m221 334 28-5 15 14-29 6Z"/><path d="m842 412 28-5 15 14-29 6Z"/></g>
      <g transform="translate(0 5)">
        <ellipse cx="153" cy="373" rx="94" ry="40" fill="#020912" opacity=".65" filter="url(#shadow)"/>
        <path d="M71 358v35c0 36 145 36 145 0v-35Z" fill="#14293a" stroke="#46657b"/>
        <ellipse cx="144" cy="357" rx="73" ry="27" fill="url(#metal)" stroke="#8099ad"/>
        <path d="m112 351-6-96 64-4 21 94c-4 23-66 30-79 6Z" fill="url(#orange)" stroke="#ad481e" strokeWidth="2"/>
        <ellipse cx="134" cy="257" rx="49" ry="46" fill="#0c1f30" stroke="#7a92a4" strokeWidth="5"/>
        <ellipse cx="134" cy="257" rx="31" ry="30" fill="url(#metal)" stroke="#263e50" strokeWidth="4"/>
        <path d="m100 224 71 48L301 144l-61-45Z" fill="url(#metal)" stroke="#37566b" strokeWidth="2"/>
        <path d="m110 221 47 34 124-118-41-31Z" fill="#8ea3b1" opacity=".3"/>
        <path d="m233 91-17 32c-1 31 50 60 69 43l25-31c17-34-55-72-77-44Z" fill="url(#orange)" stroke="#c45e29" strokeWidth="2"/>
        <ellipse cx="270" cy="116" rx="31" ry="32" transform="rotate(-30 270 116)" fill="#162b3d" stroke="#7e98a9" strokeWidth="4"/>
        <path d="m291 89 131 58-21 48-134-55Z" fill="url(#metal)" stroke="#678394" strokeWidth="2"/>
        <path d="m403 143 42 12c27 8 29 47 7 63l-43-20c-21-12-25-41-6-55Z" fill="url(#orange)" stroke="#bd5425" strokeWidth="2"/>
        <path d="m443 174 23 15-7 44-24-10Z" fill="url(#metal)" stroke="#89a5b6" strokeWidth="2"/>
        <path d="m440 224 6 27 26 8m-13-33 8 19 23-3" fill="none" stroke="#8aa4b5" strokeWidth="8" strokeLinejoin="round"/>
        <path d="M135 214c-5-82 92-167 132-126s124 43 157 60" stroke="#020a12" strokeWidth="9" fill="none"/><path d="M135 214c-5-82 92-167 132-126s124 43 157 60" stroke="#627985" strokeWidth="2" fill="none"/>
      </g>
      <ellipse cx="506" cy="399" rx="107" ry="31" fill="#152d3b" opacity=".6" filter="url(#shadow)"/>
      <g transform="translate(0 -8)">
        <path d="m415 362 119-24 64 51-121 29Z" fill="url(#car-side)" stroke="#839eb0" strokeWidth="2"/>
        <path d="m415 362 62 34 121-27v20l-121 29-62-36Z" fill="url(#car-side)"/>
        <path d="m415 362 12-23 32-6 17-25 45-9 40 25 25 7 12 38-121 27Z" fill="url(#car-top)" stroke="#e8f3fa" strokeWidth="2"/>
        <path d="m466 331 17-20 34-7 31 22-59 14Z" fill="#46677f" stroke="#b9d2df" strokeWidth="2"/>
        <path d="m485 313 4 27m33-31 7 23" stroke="#dbe8ee" strokeWidth="4"/>
        <path d="m433 354 37 24 108-24" fill="none" stroke="#fff" strokeOpacity=".8" strokeWidth="3"/>
        <path d="m481 397 1 12 94-23v-10Z" fill="#9fb5c2"/>
      </g>
      <g fill="none" stroke="#00d5ff" strokeWidth="3" strokeLinecap="round">
        <path d="m402 345-2-12 24-6m151-18 22 13v14m-164 60 18 13 18-4m132-29 19-5-3-14"/>
      </g>
      <g transform="translate(643 289)">
        <path d="m0 24 78-17 48 35-79 19Z" fill="#00d5b5" opacity=".13" stroke="#15f9d8" strokeWidth="2"/>
        <ellipse cx="64" cy="34" rx="24" ry="10" fill="none" stroke="#64ffe3" strokeWidth="2"/>
        <path d="M65 18v-53" stroke="#45e7db" strokeWidth="1.5" strokeDasharray="3 4"/>
        <rect x="9" y="-64" width="112" height="30" rx="7" fill="#07302f" stroke="#19bfae"/>
        <text x="65" y="-44" fill="#d4fff9" fontFamily="Arial,sans-serif" fontSize="13" textAnchor="middle" letterSpacing="1.5">BAKERY</text>
      </g>
      <g transform="translate(342 419)"><rect width="160" height="33" rx="7" fill="#071b2b" fillOpacity=".93" stroke="#0786bb"/><circle cx="16" cy="16" r="3" fill="#05c8ff"/><text x="29" y="21" fill="#ccefff" fontFamily="Arial,sans-serif" fontSize="12">WHEEL-LESS CAR</text></g>
      <g opacity=".5" stroke="#4b9ab6" fill="none"><path d="M37 42h26m-13-13v26M937 42h26m-13-13v26M37 566h26m-13-13v26M937 566h26m-13-13v26"/></g>
    </svg>
    <div className="scene-state-chip"><span className="pulse-dot"/><span>{state === 'IDLE' ? 'Ready for your goal' : state === 'COMPLETED' ? 'Simulation complete' : 'Symbolic mission workspace'}</span></div>
    <div className="scene-caption"><Icon name="eye" size={14}/> Illustrative scene · no measured route or live camera</div>
  </div>;
}

export function GlassesArt() {
  return <svg className="glasses-art" viewBox="0 0 330 140" role="img" aria-label="Future AR glasses companion concept">
    <defs><linearGradient id="lens"><stop stopColor="#21415d" stopOpacity=".8"/><stop offset=".6" stopColor="#0b1725"/><stop offset="1" stopColor="#08638b" stopOpacity=".6"/></linearGradient><linearGradient id="frame"><stop stopColor="#9db0c0"/><stop offset=".2" stopColor="#172a3c"/><stop offset=".6" stopColor="#020a12"/><stop offset="1" stopColor="#617b90"/></linearGradient></defs>
    <path d="m66 47 96-31 112 9 42 44-15 9-42-32-98-6-77 25Z" fill="url(#frame)" stroke="#476176" strokeWidth="2"/>
    <path d="M26 48c22-6 79-7 114 4l22 5 20-4c36-8 99-6 117 6l-7 57c-8 24-92 20-111-3l-13-36h-11l-10 35c-20 23-98 18-110-2Z" fill="url(#frame)" stroke="#7894aa" strokeWidth="2"/>
    <path d="M44 60c28-4 63-2 88 4l10 10-9 33c-13 17-69 17-82 0Z" fill="url(#lens)" stroke="#557f9b"/>
    <path d="M187 68c31-6 67-6 94 2l-5 36c-10 19-64 19-78 0Z" fill="url(#lens)" stroke="#557f9b"/>
    <path d="m46 63 35 1-28 40m149-30 36-1-29 34" fill="none" stroke="#8bd8ff" strokeOpacity=".12" strokeWidth="6"/>
    <path d="M215 91h34m-7-6 7 6-7 6" fill="none" stroke="#09caff" strokeWidth="2"/><circle cx="261" cy="91" r="6" fill="none" stroke="#43f7d6" strokeWidth="2"/>
  </svg>;
}
