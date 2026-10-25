"""Schema F "library" - used ONLY by the sealed round-4 final set. Written
after the code freeze at 36878e7; no implementation decision was made
against it. Bridge table (book_authors, undeclared FKs), a branch reachable
two ways (loan branch vs member home branch), three date columns on the
anchor, NULL tier / NULL late_fee / NULL returned_date, a genre with no
loans, punctuation-heavy author/genre names, numeric attributes of books."""
from __future__ import annotations
import pathlib, random, sqlite3

DATA = pathlib.Path(__file__).resolve().parent / "data"

F_DDL = """
CREATE TABLE genres (genre_id INTEGER PRIMARY KEY, genre_name TEXT NOT NULL);
CREATE TABLE authors (author_id INTEGER PRIMARY KEY, author_name TEXT NOT NULL, country TEXT);
CREATE TABLE books (book_id INTEGER PRIMARY KEY, title TEXT NOT NULL,
  genre_id INTEGER REFERENCES genres(genre_id), pub_year INTEGER NOT NULL, price REAL NOT NULL);
CREATE TABLE book_authors (book_id INTEGER NOT NULL, author_id INTEGER NOT NULL, PRIMARY KEY (book_id, author_id));
CREATE TABLE branches (branch_id INTEGER PRIMARY KEY, branch_name TEXT NOT NULL, city TEXT NOT NULL);
CREATE TABLE members (member_id INTEGER PRIMARY KEY, member_name TEXT NOT NULL,
  branch_id INTEGER REFERENCES branches(branch_id), joined_on TEXT NOT NULL, tier TEXT);
CREATE TABLE loans (loan_id INTEGER PRIMARY KEY, member_id INTEGER NOT NULL REFERENCES members(member_id),
  book_id INTEGER NOT NULL REFERENCES books(book_id), branch_id INTEGER NOT NULL REFERENCES branches(branch_id),
  loan_date TEXT NOT NULL, due_date TEXT NOT NULL, returned_date TEXT, late_fee REAL);
"""
F_EDGES = {
    ("books", "genre_id", "genres", "genre_id"),
    ("book_authors", "book_id", "books", "book_id"),
    ("book_authors", "author_id", "authors", "author_id"),
    ("members", "branch_id", "branches", "branch_id"),
    ("loans", "member_id", "members", "member_id"),
    ("loans", "book_id", "books", "book_id"),
    ("loans", "branch_id", "branches", "branch_id"),
}


def build_f(path=None):
    path = pathlib.Path(path or DATA / "library.db"); path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    rng = random.Random(31337)
    c = sqlite3.connect(str(path)); c.executescript(F_DDL)
    c.executemany("INSERT INTO genres VALUES (?,?)", [
        (1, "Sci-Fi & Fantasy"), (2, "Children's"), (3, "Non-Fiction (History)"), (4, "Poetry"), (5, "Mystery")])  # 4 unused
    c.executemany("INSERT INTO authors VALUES (?,?,?)", [
        (1, "Ursula K. Le Guin", "USA"), (2, "J.R.R. Tolkien", "UK"), (3, "N. K. Jemisin", "USA"),
        (4, "Anonymous", None), (5, "Dr. Seuss", "USA"), (6, "Agatha Christie", "UK")])
    books = [(1, "The Dispossessed", 1, 1974, 14.5), (2, "The Hobbit", 1, 1937, 12.0), (3, "The Fifth Season", 1, 2015, 17.0),
             (4, "Green Eggs and Ham", 2, 1960, 8.5), (5, "Murder on the Orient Express", 5, 1934, 11.0),
             (6, "A People's History", 3, 1980, 22.0), (7, "Good Omens", 1, 1990, 16.0), (8, "Folk Tales", 3, 2005, 9.0),
             (9, "Lost Poems", None, 2010, 7.5)]
    c.executemany("INSERT INTO books VALUES (?,?,?,?,?)", books)
    c.executemany("INSERT INTO book_authors VALUES (?,?)", [
        (1, 1), (2, 2), (3, 3), (4, 5), (5, 6), (6, 4), (7, 1), (7, 3), (8, 4), (9, 4)])
    c.executemany("INSERT INTO branches VALUES (?,?,?)", [
        (1, "Central Library", "Springfield"), (2, "Riverside Branch", "Shelbyville"), (3, "Hilltop Annex", "Springfield")])
    c.executemany("INSERT INTO members VALUES (?,?,?,?,?)", [
        (i, f"Member {i:03d}", rng.choice([1, 2, 3, None]), f"{rng.choice([2023, 2024, 2025])}-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}",
         rng.choice(["Gold", "Silver", None])) for i in range(1, 51)])
    loans = []
    for l in range(1, 501):
        m = rng.randint(1, 12); d = rng.randint(1, 20)
        ld = f"2025-{m:02d}-{d:02d}"; due = f"2025-{m:02d}-{d + 7:02d}"
        ret = None if rng.random() < 0.2 else f"2025-{min(m + (1 if rng.random() < 0.5 else 0), 12):02d}-{rng.randint(1, 28):02d}"
        fee = None if rng.random() < 0.5 else round(rng.uniform(0.5, 9), 2)
        loans.append((l, rng.randint(1, 50), rng.randint(1, 9), rng.choice([1, 2, 3]), ld, due, ret, fee))
    c.executemany("INSERT INTO loans VALUES (?,?,?,?,?,?,?,?)", loans)
    c.commit(); c.close()
    return path

if __name__ == "__main__":
    print(build_f())
