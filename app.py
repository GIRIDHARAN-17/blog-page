from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from bson.objectid import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()


app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET")
app.config["MONGO_URI"] = os.environ.get("MONGO_URI")
mongo = PyMongo(app)
bcrypt = Bcrypt(app)

users_col = mongo.db.users
posts_col = mongo.db.posts

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return users_col.find_one({"_id": ObjectId(uid)})

def user_by_username(username):
    return users_col.find_one({"username": username})

def format_dt(iso_str):
    dt = datetime.fromisoformat(iso_str)
    return dt.strftime("%Y-%m-%d %H:%M:%S ")

@app.route("/")
def index():
    posts = posts_col.find().sort("created_at", -1)
    # join author username
    posts_list = []
    for p in posts:
        author = users_col.find_one({"_id": p["author_id"]})
        posts_list.append({
            "id": str(p["_id"]),
            "title": p["title"],
            "body": p["body"],
            "author": author["username"] if author else "unknown",
            "created_at": p["created_at"],
            "created_at_readable": format_dt(p["created_at"])
        })
    return render_template("index.html", posts=posts_list, user=current_user())


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Username and password required.", "error")
            return redirect(url_for("signup"))
        if users_col.find_one({"username": username}):
            flash("Username already taken.", "error")
            return redirect(url_for("signup"))
        pw_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        user_id = users_col.insert_one({
            "username": username,
            "password": pw_hash,
            "created_at": datetime.utcnow().isoformat()
        }).inserted_id
        session["user_id"] = str(user_id)
        flash("Signup successful. Logged in.", "success")
        return redirect(url_for("index"))
    return render_template("signup.html", user=current_user())

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = users_col.find_one({"username": username})
        if not user:
            flash("Invalid username or password.", "error")
            return redirect(url_for("login"))
        if bcrypt.check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            flash("Logged in.", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password.", "error")
            return redirect(url_for("login"))
    return render_template("login.html", user=current_user())

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logged out.", "success")
    return redirect(url_for("index"))


@app.route("/post/create", methods=["GET", "POST"])
def create_post():
    user = current_user()
    if not user:
        flash("You must be logged in to create a post.", "error")
        return redirect(url_for("login"))
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        if not title:
            flash("Title is required.", "error")
            return redirect(url_for("create_post"))
        post = {
            "title": title,
            "body": body,
            "author_id": user["_id"],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": None
        }
        posts_col.insert_one(post)
        flash("Post created.", "success")
        return redirect(url_for("index"))
    return render_template("create_post.html", user=user)

@app.route("/post/<post_id>")
def view_post(post_id):
    p = posts_col.find_one({"_id": ObjectId(post_id)})
    if not p:
        flash("Post not found.", "error")
        return redirect(url_for("index"))
    author = users_col.find_one({"_id": p["author_id"]})
    return render_template("view_post.html", post={
        "id": str(p["_id"]),
        "title": p["title"],
        "body": p["body"],
        "author": author["username"] if author else "unknown",
        "created_at": p["created_at"],
        "created_at_readable": format_dt(p["created_at"]),
        "updated_at": p["updated_at"]
    }, user=current_user())

@app.route("/post/<post_id>/edit", methods=["GET", "POST"])
def edit_post(post_id):
    user = current_user()
    if not user:
        flash("Login required.", "error")
        return redirect(url_for("login"))
    p = posts_col.find_one({"_id": ObjectId(post_id)})
    if not p:
        flash("Post not found.", "error")
        return redirect(url_for("index"))
    if p["author_id"] != user["_id"]:
        flash("You can only edit your own posts.", "error")
        return redirect(url_for("view_post", post_id=post_id))
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        posts_col.update_one({"_id": p["_id"]}, {"$set": {
            "title": title,
            "body": body,
            "updated_at": datetime.utcnow().isoformat()
        }})
        flash("Post updated.", "success")
        return redirect(url_for("view_post", post_id=post_id))
    return render_template("edit_post.html", post={
        "id": str(p["_id"]),
        "title": p["title"],
        "body": p["body"]
    }, user=user)

@app.route("/post/<post_id>/delete", methods=["POST"])
def delete_post(post_id):
    user = current_user()
    if not user:
        flash("Login required.", "error")
        return redirect(url_for("login"))
    p = posts_col.find_one({"_id": ObjectId(post_id)})
    if not p:
        flash("Post not found.", "error")
        return redirect(url_for("index"))
    if p["author_id"] != user["_id"]:
        flash("You can only delete your own posts.", "error")
        return redirect(url_for("view_post", post_id=post_id))
    posts_col.delete_one({"_id": p["_id"]})
    flash("Post deleted.", "success")
    return redirect(url_for("index"))

@app.route("/users")
def users():
    """List all users with their blog counts."""
    users_cursor = users_col.find()
    users_list = []
    for u in users_cursor:
        count = posts_col.count_documents({"author_id": u["_id"]})
        users_list.append({
            "username": u["username"],
            "id": str(u["_id"]),
            "count": count
        })
    return render_template("users.html", users=users_list, user=current_user())

@app.route("/user/<username>")
def user_detail(username):
    """Show details of specific user including blog count and optionally titles."""
    u = users_col.find_one({"username": username})
    if not u:
        flash("User not found.", "error")
        return redirect(url_for("users"))
    posts_cursor = posts_col.find({"author_id": u["_id"]}).sort("created_at", -1)
    posts_list = []
    for p in posts_cursor:
        posts_list.append({
            "title": p["title"],
            "id": str(p["_id"]),
            "created_at": p["created_at"],
            "created_at_readable": format_dt(p["created_at"])
        })
    return render_template("user_detail.html", profile={
        "username": u["username"],
        "id": str(u["_id"]),
        "created_at": u.get("created_at")
    }, posts=posts_list, count=len(posts_list), user=current_user())

@app.route("/stats/total_users")
def stats_total_users():
    total = users_col.count_documents({})
    return jsonify({"total_users": total})

@app.route("/stats/users_blogs")
def stats_users_blogs():
    pipeline = [
        {"$lookup": {
            "from": "posts",
            "localField": "_id",
            "foreignField": "author_id",
            "as": "posts"
        }},
        {"$project": {
            "username": 1,
            "blogs_count": {"$size": "$posts"}
        }},
        {"$sort": {"blogs_count": -1, "username": 1}}
    ]
    results = list(users_col.aggregate(pipeline))
    response = [{"username": r["username"], "blogs_count": r["blogs_count"]} for r in results]
    return jsonify(response)

@app.route("/api/user/<username>")
def api_user_detail(username):
    """Return user details, blog count, and optionally titles (JSON)."""
    u = users_col.find_one({"username": username})
    if not u:
        return jsonify({"error": "user not found"}), 404
    posts_cursor = posts_col.find({"author_id": u["_id"]})
    posts_list = [{"id": str(p["_id"]), "title": p["title"], "created_at": p["created_at"]} for p in posts_cursor]
    return jsonify({
        "username": u["username"],
        "user_id": str(u["_id"]),
        "blog_count": len(posts_list),
        "posts": posts_list
    })


if __name__ == "__main__":
    app.run(debug=True)
