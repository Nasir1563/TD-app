from flask import Flask, request, redirect, url_for, render_template_string
from bs4 import BeautifulSoup
import pandas as pd
from supabase import create_client, Client
import os
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)


# Initialize Supabase client
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    logging.error("Supabase URL or Key is not set. Check your .env file.")
else:
    logging.debug(f"Supabase URL: {SUPABASE_URL}")
    logging.debug(f"Supabase Key: {SUPABASE_KEY}")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def index():
    message = request.args.get('message', '')
    message_class = request.args.get('message_class', '')

    html = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Trade History Dashboard</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f4f4f4;
            }
            .container {
                width: 80%;
                margin: 0 auto;
                overflow: hidden;
            }
            header {
                background: #50b3a2;
                color: #fff;
                padding-top: 30px;
                min-height: 70px;
                border-bottom: #e8491d 3px solid;
            }
            header a {
                color: #fff;
                text-decoration: none;
                text-transform: uppercase;
                font-size: 16px;
            }
            header ul {
                padding: 0;
                list-style: none;
            }
            header li {
                float: left;
                display: inline;
                padding: 0 20px 0 20px;
            }
            header #branding {
                float: left;
            }
            header #branding h1 {
                margin: 0;
            }
            header nav {
                float: right;
                margin-top: 10px;
            }
            header .highlight, header .current a {
                color: #e8491d;
                font-weight: bold;
            }
            header a:hover {
                color: #cccccc;
                font-weight: bold;
            }
            #main {
                padding: 20px;
                background: #fff;
                margin-top: 20px;
            }
            #upload-form {
                background: #fff;
                padding: 20px;
                margin-top: 20px;
                border: 1px #ddd solid;
            }
            .message {
                padding: 10px;
                margin-bottom: 20px;
                border-radius: 5px;
                font-size: 16px;
                text-align: center;
            }
            .success {
                background-color: #dff0d8;
                color: #3c763d;
                border: 1px solid #d6e9c6;
            }
            .error {
                background-color: #f2dede;
                color: #a94442;
                border: 1px solid #ebccd1;
            }
        </style>
    </head>
    <body>
        <header>
            <div class="container">
                <div id="branding">
                    <h1>Trade History Dashboard</h1>
                </div>
                <nav>
                    <ul>
                        <li><a href="/">Home</a></li>
                    </ul>
                </nav>
            </div>
        </header>
        <section id="main" class="container">
            {% if message %}
            <div class="message {{ message_class }}">{{ message }}</div>
            {% endif %}
            <div id="upload-form">
                <h2>Upload Trade History Report</h2>
                <form method="POST" action="/upload" enctype="multipart/form-data">
                    <input type="file" name="file" />
                    <input type="submit" value="Upload" />
                </form>
            </div>
        </section>
    </body>
    </html>
    '''
    return render_template_string(html, message=message, message_class=message_class)

@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    if file:
        try:
            content = file.read().decode('utf-16')
            soup = BeautifulSoup(content, 'html.parser')
            
            # Extract the first table from the HTML
            table = soup.find('table')
            
            if not table:
                logging.error("Positions table not found in the HTML file.")
                return redirect(url_for('index', message="Positions table not found in the HTML file.", message_class="error"))
            
            # Extract headers
            headers = [header.text.strip() for header in table.find_all('th')]
            
            # Extract rows, handling hidden columns properly
            rows = []
            stop_processing = False
            for row in table.find_all('tr')[1:]:
                if stop_processing:
                    break
                if row.find('th', colspan="14"):
                    th_text = row.find('th', colspan="14").text.strip()
                    if "orders" in th_text.lower():
                        stop_processing = True
                        break
                cols = []
                for col in row.find_all('td'):
                    if 'hidden' in col.get('class', []):
                        continue
                    text = col.text.strip()
                    colspan = int(col.get('colspan', 1))
                    cols.extend([text] * colspan)
                if not stop_processing:
                    rows.append(cols)
            
            # Clean and normalize the rows
            cleaned_rows = [row for row in rows if any(row)]
            max_columns = max(len(row) for row in cleaned_rows)
            normalized_rows = [row + [''] * (max_columns - len(row)) for row in cleaned_rows]
            
            # Define the expected columns with standardized names
            columns = ['time', 'position', 'symbol', 'type', 'volume', 'price', 's_l', 't_p', 'close_time', 'close_price', 'commission', 'swap', 'profit']
            columns += [f'extra{i}' for i in range(len(normalized_rows[0]) - len(columns))]
            
            # Create DataFrame
            df = pd.DataFrame(normalized_rows, columns=columns)
            
            # Drop the header row
            df = df.drop(0)
            
            # Select only the relevant columns
            df_selected = df.loc[:, ['time', 'position', 'symbol', 'type', 'volume', 'price', 's_l', 't_p', 'close_time', 'close_price', 'commission', 'swap', 'profit']]
            
            # Convert relevant columns to appropriate types
            df_selected.loc[:, 'time'] = pd.to_datetime(df_selected['time'], errors='coerce')
            df_selected.loc[:, 'position'] = pd.to_numeric(df_selected['position'], errors='coerce')
            df_selected.loc[:, 'volume'] = pd.to_numeric(df_selected['volume'], errors='coerce')
            df_selected.loc[:, 'price'] = pd.to_numeric(df_selected['price'], errors='coerce')
            df_selected.loc[:, 's_l'] = pd.to_numeric(df_selected['s_l'], errors='coerce')
            df_selected.loc[:, 't_p'] = pd.to_numeric(df_selected['t_p'], errors='coerce')
            df_selected.loc[:, 'close_time'] = pd.to_datetime(df_selected['close_time'], errors='coerce')
            df_selected.loc[:, 'close_price'] = pd.to_numeric(df_selected['close_price'], errors='coerce')
            df_selected.loc[:, 'commission'] = pd.to_numeric(df_selected['commission'], errors='coerce')
            df_selected.loc[:, 'swap'] = pd.to_numeric(df_selected['swap'], errors='coerce')
            df_selected.loc[:, 'profit'] = pd.to_numeric(df_selected['profit'], errors='coerce')

            # Convert DataFrame to dictionary and handle Timestamp objects
            data = df_selected.astype(str).to_dict(orient='records')

            # Insert data into Supabase
            response = supabase.table('trade_history').insert(data).execute()

            logging.debug(f"Supabase response: {response}")

            if response.data:
                return redirect(url_for('index', message="Trade data uploaded successfully to the database.", message_class="success"))
            else:
                logging.error(f"Data upload failed: {response.error}")
                return redirect(url_for('index', message="Data upload failed.", message_class="error"))
        
        except Exception as e:
            logging.error(f"An error occurred while processing the file: {e}", exc_info=True)
            return redirect(url_for('index', message="An error occurred while processing the file.", message_class="error"))
    
    logging.error("No file uploaded.")
    return redirect(url_for('index', message="No file uploaded.", message_class="error"))


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))  # Use the PORT environment variable if available
    app.run(host='0.0.0.0', port=port)
