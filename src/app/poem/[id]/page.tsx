import getPoems from "@/apis/getPoems";
import Link from "next/link";

import fs from "node:fs"

export default function Poem({ params }: { params: { id:number } }) {

  let content = fs.readFileSync( process.cwd() + `/public/text/${params.id}.txt`).toString();
  let br = content.indexOf('\n');
  let meta = content.slice(0, br).split('|');
  let poem:Poem = {
    title: meta[0] ?? "无题",
    extra: meta[1] ?? undefined,
    content: content.slice(br + 2),
  };

  return <div className="h-screen w-screen overflow-auto">
    <Link href="/" className="cursor-default"><div className="z-0 bg-[#00000045] fixed w-screen h-screen top-0"></div></Link>
    <div className="relative z-10 top-0 w-1/2 min-w-[40rem] bg-[#ffffed] m-auto p-5 rounded shadow-2xl mb-20 mt-20 outline-dashed">
      <div className="flex flex-row justify-between items-baseline font-bold">
        <div className="text-3xl">{poem.title}</div>
        <div>{poem.extra}</div>
      </div>
      <div className="mt-5 mb-1 text-xl">
        {poem.content.split('\n').map((line) => (<>{line}<br/></>))}
      </div>
    </div>
  </div>
}

export function generateStaticParams(){

  let poems = getPoems();

  return poems.map(poem=>({id: poem.id.toString()}));
  
}
