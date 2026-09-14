# In-Library Use Desk
A simple self-checkout and check-in application for library reading rooms.

The application works with an existing **Koha** installation to verify patrons and library items, while maintaining its own separate database for reading-room usage records.

## Features

* Patron lookup from Koha
* Item/barcode lookup from Koha
* Self-issue books for reading-room use
* Self-return/check-in
* Supports configurable item types
* Separate database for in-house usage records
* Read-only access to Koha data
* Simple Flask web interface
* Can be run directly with Python or behind Gunicorn/Nginx

## Requirements

* Debian/Ubuntu Linux
* Python 3
* Python virtual environment
* MySQL/MariaDB
* Existing Koha installation
* Koha database access
* Nginx (optional, for production deployment)

## Installation

### 1. Create the application directory

```bash
sudo mkdir -p /opt/ilud
sudo chown $USER:$USER /opt/ilud
cd /opt/ilud
```

Copy the application files into this directory:

```text
/opt/ilud/
├── app.py
├── requirements.txt
├── schema.sql
├── README.md
├── templates/
└── static/
```

---

### 2. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip \
default-libmysqlclient-dev build-essential nginx
```

---

### 3. Find your Koha database name

First list the installed Koha instances:

```bash
sudo koha-list
```

Then check the database configuration:

```bash
sudo cat /etc/koha/sites/<instance>/koha-conf.xml | grep -A1 '<database>'
```

Replace `<instance>` with your Koha instance name.

For the examples below, the Koha database is assumed to be:

```text
koha_library
```

If your database has a different name, replace `koha_library` accordingly.

---

### 4. Create the application database

The included `schema.sql` creates the separate database:

```text
koha_self
```

Run:

```bash
mysql -u root -p < schema.sql
```

This creates the application's own database and table.

The application does **not** store its reading-room records inside the Koha database.

---

### 5. Create the MySQL user

Log in to MySQL/MariaDB:

```bash
sudo mysql -u root -p
```

Create the application database user:

```sql
CREATE USER 'koha_self'@'localhost'
IDENTIFIED BY 'koha_self123';
```

Give the application read-only access to the required Koha tables:

```sql
GRANT SELECT ON koha_library.borrowers
TO 'koha_self'@'localhost';

GRANT SELECT ON koha_library.items
TO 'koha_self'@'localhost';

GRANT SELECT ON koha_library.biblio
TO 'koha_self'@'localhost';

GRANT SELECT ON koha_library.biblioitems
TO 'koha_self'@'localhost';
```

Give the application read/write access only to its own database:

```sql
GRANT SELECT, INSERT, UPDATE
ON koha_self.in_house_use
TO 'koha_self'@'localhost';
```

Apply the privileges:

```sql
FLUSH PRIVILEGES;
```

Exit:

```sql
EXIT;
```

### Database permissions

The application user has the following access:

| Database       | Table          | Permission             |
| -------------- | -------------- | ---------------------- |
| `koha_library` | `borrowers`    | SELECT                 |
| `koha_library` | `items`        | SELECT                 |
| `koha_library` | `biblio`       | SELECT                 |
| `koha_library` | `biblioitems`  | SELECT                 |
| `koha_self`    | `in_house_use` | SELECT, INSERT, UPDATE |

This keeps the application from modifying Koha's own data.

---

## 6. Create the Python virtual environment

Go to the application directory:

```bash
cd /opt/reading-room-desk
```

Create the virtual environment:

```bash
python3 -m venv venv
```

Activate it:

```bash
source venv/bin/activate
```

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

The `requirements.txt` file contains:

```text
Flask==3.0.3
PyMySQL==1.1.1
gunicorn
```

If Gunicorn is not already included in the requirements file:

```bash
pip install gunicorn
```

---

## 7. Configure the environment

Create the environment file:

```bash
cat > /opt/ilud/.env << 'EOF'
KOHA_DB_HOST=127.0.0.1
KOHA_DB_PORT=3306
KOHA_DB_USER=koha_self
KOHA_DB_PASSWORD=koha_self123
KOHA_DB_NAME=koha_library
SELF_DB_NAME=koha_self
ALLOWED_ITEM_TYPES=BK,REF
EOF
```

Protect the file:

```bash
chmod 600 /opt/ilud/.env
```

### Configuration

| Variable             | Description                                  |
| -------------------- | -------------------------------------------- |
| `KOHA_DB_HOST`       | Koha database server                         |
| `KOHA_DB_PORT`       | MySQL/MariaDB port                           |
| `KOHA_DB_USER`       | Application database user                    |
| `KOHA_DB_PASSWORD`   | Application database password                |
| `KOHA_DB_NAME`       | Koha database name                           |
| `SELF_DB_NAME`       | Application's own database                   |
| `ALLOWED_ITEM_TYPES` | Koha item types allowed for reading-room use |

By default:

```text
ALLOWED_ITEM_TYPES=BK,REF
```

Only items belonging to these item types can be used through the application.

---

## 8. Manual test

Activate the virtual environment:

```bash
cd /opt/ilud
source venv/bin/activate
```

Load the environment variables:

```bash
sudo su
set -a
source .env
set +a
```

Start the application:

```bash
python app.py
```

The application should be available at:

```text
http://<server-ip>:5050
```

For example:

```text
http://192.168.29.2:5050
```

## 9. systemd service

Create the service:

```bash
sudo tee /etc/systemd/system/ilud.service > /dev/null << 'EOF'
[Unit]
Description=Reading Room Desk
After=network.target mysql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/ilud
EnvironmentFile=/opt/ilud/.env
ExecStart=/opt/ilud/venv/bin/gunicorn -w 2 -b 0.0.0.0:5050 app:app
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

Set permissions and start the service:

```bash
sudo chown -R www-data:www-data /opt/ilud
sudo systemctl daemon-reload
sudo systemctl enable --now ilud
```

Check status:

```bash
sudo systemctl status ilud
```

View logs:

```bash
sudo journalctl -u ilud -f
```

After making changes to the application:

```bash
sudo systemctl restart ilud
```

The application will be available at:

```text
http://<server-ip>:5050
```

Open the address in a browser and test:

1. Patron lookup
2. Barcode/item lookup
3. Issue an item
4. Return the item
5. Verify the usage record

Stop the application with:

```text
Ctrl+C
```

---

## Database Structure

The application uses a separate database from Koha.

```text
Koha
└── koha_library
    ├── borrowers
    ├── items
    ├── biblio
    └── biblioitems

Reading Room Desk
└── koha_self
    └── in_house_use
```

The separation is intentional:

* Koha remains the source of patron and item information.
* Reading-room transactions are stored separately.
* The application does not modify Koha circulation records.
* Removing the application database does not affect Koha's main circulation data.

## Application Flow

```text
                 ┌─────────────────────┐
                 │   Reading Room Desk │
                 │      Flask App      │
                 └──────────┬──────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
     ┌─────────────────┐       ┌──────────────────┐
     │   Koha Database │       │ Application DB   │
     │  koha_library   │       │   koha_self      │
     ├─────────────────┤       ├──────────────────┤
     │ borrowers       │       │ in_house_use     │
     │ items           │       └──────────────────┘
     │ biblio          │
     │ biblioitems     │
     └─────────────────┘
```

## Security Notes

The application database user is deliberately restricted.

It has:

* `SELECT` access to the required Koha tables
* `SELECT`, `INSERT`, and `UPDATE` access to its own table
* No permission to modify Koha patron, item, bibliographic, or circulation data

The `.env` file contains database credentials and should never be committed to Git.

Add it to `.gitignore`:

```bash
echo ".env" >> .gitignore
echo "venv/" >> .gitignore
```

## Project Structure

```text
ilud/
├── app.py
├── requirements.txt
├── schema.sql
├── README.md
├── .gitignore
├── templates/
│   └── ...
├── static/
│   ├── css/
│   ├── js/
│   └── ...
└── venv/
```

The `venv/` directory should not be committed to Git.

## Production Deployment

For a production installation, it is recommended to run the Flask application using **Gunicorn** and place **Nginx** in front of it.

A typical setup is:

```text
Browser
   │
   ▼
 Nginx
   │
   ▼
Gunicorn
   │
   ▼
 Flask Application
   │
   ├──► Koha MariaDB
   │
   └──► koha_self MariaDB
```

A systemd service can also be created so that the application starts automatically after a server reboot.

## License

Add your preferred license here.

## Author

**Mahesh Palamuttath**

Library Technologist
Linux, FOSS & Library Technology

Website: https://maheshpalamuttath.info/
