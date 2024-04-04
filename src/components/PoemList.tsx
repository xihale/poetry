import getPoems from "@/apis/getPoems"
import Link from "next/link";

export default function PoemList(){

  let poems = getPoems();

  return <>
    <ul className="flex w-screen h-screen pt-20 pb-20 pl-10 pr-10 flex-wrap justify-center fixed overflow-x-auto">
      {poems.map((d)=>
        <li key={d.id} className="w-80 h-2/5 m-5 p-5 rounded shadow-xl hover:outline-dashed bg-[#ffffed]">
            <Link href={`/poem/${d.id}`} className="hover:cursor-default">
            <div className="flex flex-row justify-between items-baseline font-bold">
              <div className="text-2xl">{d.title}</div>
              <div>{d.extra}</div>
            </div>
            <div className="overflow-hidden h-3/4 mt-5">
              {d.brief.map((b)=>(<>{b}<br/></>))}
            </div>
            ......
            </Link>

        </li>)}
    </ul>
  </>
}

