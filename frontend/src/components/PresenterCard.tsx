import { Segment } from '../api'
export function PresenterCard({segment,index,total}:{segment:Segment;index:number;total:number}){return <article className="presenter" aria-live="polite"><div className="eyebrow">AI Presenter · Section {index+1} of {total}</div><p>{segment.text}</p></article>}
