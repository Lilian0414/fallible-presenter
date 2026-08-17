import { FormEvent, useState } from 'react'
export function SourceInput({onStart,busy}:{onStart:(text:string)=>void;busy:boolean}) {
  const [text,setText]=useState('Water freezes at zero degrees Celsius. Exercise improves cardiovascular health. Plants convert light into energy. The Moon orbits Earth. Bees pollinate many flowering plants. Regular sleep supports memory. Oceans cover 71% of Earth.')
  function submit(event:FormEvent){event.preventDefault();onStart(text)}
  return <form onSubmit={submit} className="source-form"><label htmlFor="source">Source text</label><textarea id="source" rows={11} value={text} onChange={e=>setText(e.target.value)} minLength={40} required/><p className="hint">Paste at least five clear, sentence-like statements. Your text stays in this session.</p><button disabled={busy||text.length<40}>{busy?'Preparing presentation…':'Start Presentation'}</button></form>
}
