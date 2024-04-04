import getPoems from "@/apis/getPoems";
import Link from "next/link";

import fs from "node:fs"

import styles from "./page.module.scss";

export default function Poem({ params }: { params: { id:number } }) {

  let content = fs.readFileSync( process.cwd() + `/src/text/${params.id}.txt`).toString();
  let br = content.indexOf('\n');
  let meta = content.slice(0, br).split('|');
  let poem:Poem = {
    title: meta[0] ?? "无题",
    extra: meta[1] ?? undefined,
    content: content.slice(br + 2),
  };

  return <div className={styles.container}>
    <Link href="/"><div className={styles.back}></div></Link>
    <div className={styles.poem}>
      <div className={styles.meta}>
        <div className={styles.title}>{poem.title}</div>
        <div>{poem.extra}</div>
      </div>
      <div className={styles.content}>
        {poem.content.split('\n').map((line) => (<>{line}<br/></>))}
      </div>
    </div>
  </div>
}

export function generateStaticParams(){

  let poems = getPoems();

  return poems.map(poem=>({id: poem.id.toString()}));
  
}
