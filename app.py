import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]

    result = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    user_cash = result[0]["cash"]

    holdings = db.execute(" SELECT symbol, SUM(shares) AS net_shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING net_shares > 0", user_id)

    portfolio = []
    total_portfolio_value = 0

    for stock in holdings:
        symbol = stock["symbol"]
        shares = stock["net_shares"]
        quote = lookup(symbol)

        if quote:
            current_price = quote["price"]
            total_value = current_price * shares
            total_portfolio_value += total_value

            portfolio.append({
                "symbol": symbol,
                "shares": shares,
                "current_price": current_price,
                "total_value": total_value
            })

    grand_total = total_portfolio_value + user_cash

    return render_template("index.html", portfolio = portfolio, Cash = user_cash, Grand_total = grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """buy stock"""
    user_id = session["user_id"]

    if request.method == "POST":
        symbol = request.form.get("symbol")
        try:
            quant = int(request.form.get("shares"))
        except ValueError:
            return apology("Please enter a valid input!", 400)

        quote = lookup(symbol)

        if not quote:
            return apology("Stock doesn't exists!", 400)

        if quant < 1:
            return apology("Please input a valid amount!", 400)

        stock_price = quote["price"]

        req_amount = stock_price * quant
        av_amount = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]


        if av_amount < req_amount:
            return apology("Not enought balance!")

        up_amount = av_amount - req_amount

        db.execute("UPDATE users SET cash = ? WHERE id = ?", up_amount, user_id)

        db.execute("INSERT INTO transactions(user_id, symbol, shares, price, status) VALUES(?, ?, ?, ?, ?)", user_id, quote["symbol"], quant, stock_price, 'buy')

        flash("Bought!")

        return redirect("/")

    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    user_id  = session["user_id"]

    transactions = db.execute("SELECT * FROM transactions WHERE user_id = ?", user_id)
    return render_template("history.html", transactions = transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")



@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")



@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        stock = request.form.get("symbol")

        if not stock:
            return apology("Please enter a stock symbol", 400)
        quote = lookup(stock)

        if quote:
            return render_template("quoted.html", quote = quote)
        else:
            return apology("Stock not found!", 400)
    return render_template("quote.html")



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    username = request.form.get("username")
    password = request.form.get("password")
    confirmation = request.form.get("confirmation")

    if request.method == "POST":
        if not username:
            return apology("Provide a name.", 400)

        if not password:
            return apology("Provide a password.", 400)

        if  confirmation != password:
            return apology("Password did not match.", 400)

        try:
            db.execute("INSERT INTO users( username, hash) VALUES( ?, ?)", username, generate_password_hash(password))
        except ValueError:
            return apology("Username already exists.", 400)

        return redirect("/login")

    else:
        return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]

    if request.method == "POST":

        stocks = db.execute("SELECT symbol, SUM(shares) AS net_shares FROM transactions WHERE user_id = ? GROUP BY symbol", user_id)
        stock = request.form.get("symbol")

        stock_info = next((s for s in stocks if s["symbol"] == stock),None)
        if not stock_info:
           return apology("Stock you din't own!", 400)

        try:
            quant = int(request.form.get("shares"))
            if quant <= 0:
                return apology("Please enter a positive input!", 400)
        except ValueError:
            return apology("Please enter a valid input!", 400)

        if quant > int(stock_info["net_shares"]):
            return apology("Not enough shares to sell!", 400)

        quote = lookup(stock)
        current_price = quote["price"]

        sell_value = current_price * quant

        av_amount = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
        up_amount = av_amount + sell_value
        db.execute("UPDATE users SET cash = ? WHERE id = ?", up_amount, user_id )

        db.execute("INSERT INTO transactions(user_id, symbol, shares, price, status) VALUES(?, ?, ?, ?, ?)", user_id, stock, -quant, current_price, 'sell')

        flash("Sold")
        return redirect("/")


    else:
        stocks = db.execute("SELECT symbol FROM transactions WHERE user_id = ? GROUP BY symbol", user_id)
        return render_template("sell.html", stocks = stocks)

@app.route("/load", methods = ["GET", "POST"])
@login_required
def load():

    user_id = session["user_id"]

    if request.method == "POST":
        try:
            cash = float(request.form.get("cash"))
            if cash <= 0:
                return apology("Please enter a positive amount!", 403)
        except ValueError:
            return apology("Please enter a valid amount!", 403)

        result = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        user_cash = result[0]["cash"]

        up_cash = user_cash + cash

        db.execute("UPDATE users SET cash = ? WHERE id = ?", up_cash, user_id)

        return redirect("/")

    else:
        return render_template("load.html")

