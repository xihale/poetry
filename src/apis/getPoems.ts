
import fs from "node:fs"

export default function getPoems(){

  let poemIds = fs.readdirSync("src/text").map((f)=>parseInt(f.split(".")[0])).sort((a,b)=>a-b);

  let poems:PoemBrief[] = [];

  poemIds.forEach(id => {
    let content = fs.readFileSync("src/text/"+id+".txt").toString();
    let meta = content.slice(0, content.indexOf("\n")).split('|');
    poems.push({
      id: id,
      title: meta[0] ?? content,
      extra: meta[1] ?? undefined,
      brief: content?.split("\n").slice(2,12)
    });
  });

  return poems;

}
