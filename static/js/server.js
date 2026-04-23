const express=require("express");
const cors=require("cors");
const bcrypt=require("bcrypt");
const jwt=require("jsonwebtoken");
const multer=require("multer");
const {Pool}=require("pg");

const app=express();
app.use(cors());
app.use(express.json());
app.use("/uploads",express.static("uploads"));

const pool=new Pool({
 connectionString:process.env.DATABASE_URL,
 ssl:{rejectUnauthorized:false}
});

const storage=multer.diskStorage({
 destination:"uploads/",
 filename:(req,file,cb)=>cb(null,Date.now()+"-"+file.originalname)
});
const upload=multer({storage});

function auth(req,res,next){
 const t=req.headers.authorization;
 if(!t) return res.sendStatus(401);
 try{
  req.user=jwt.verify(t,process.env.JWT_SECRET);
  next();
 }catch{res.sendStatus(403);}
}

app.get("/",(req,res)=>res.send("API OK"));

app.post("/api/register",async(req,res)=>{
 const {username,password}=req.body;
 const hash=await bcrypt.hash(password,10);
 try{
  const r=await pool.query(
   "INSERT INTO users(username,password) VALUES($1,$2) RETURNING *",
   [username,hash]
  );
  res.json(r.rows[0]);
 }catch{res.status(400).json({error:"exists"});}
});

app.post("/api/login",async(req,res)=>{
 const {username,password}=req.body;
 const r=await pool.query("SELECT * FROM users WHERE username=$1",[username]);
 if(!r.rows.length) return res.status(400).json({error:"no user"});
 const ok=await bcrypt.compare(password,r.rows[0].password);
 if(!ok) return res.status(400).json({error:"wrong"});
 const token=jwt.sign({id:r.rows[0].id},process.env.JWT_SECRET);
 res.json({token});
});

app.post("/api/upload",auth,upload.single("image"),(req,res)=>{
 res.json({file:req.file.filename});
});

const PORT=process.env.PORT||3000;
app.listen(PORT,()=>console.log("run "+PORT));
