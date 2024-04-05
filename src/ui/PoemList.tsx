import getPoems from "@/apis/getPoems"

import styles from  "./PoemList.module.scss"
import Link from "next/link";

export default function PoemList(){

  let poems = getPoems();

  return <>
    <div className={styles.container}>
      {poems.map((d)=>
        <Link href={`/${d.id}`} key={d.id} className={styles.card}>
          <div className={styles.meta}>
            <div className={styles.title}>{d.title}</div>
            <div>{d.extra}</div>
          </div>
          <div className={styles.brief}>
            {d.brief.map((b,i)=>(<><span key={i}>{b}</span><br/></>))}
          </div>
          <span>......</span>
        </Link>
      )}
    </div>
  </>
}
