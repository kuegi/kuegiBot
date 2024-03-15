from datetime import datetime
import os
import re
import json
import pandas as pd


def history_file_name(index, exchange, symbol):
    """
    Generates a filename for a history file based on index, exchange, and symbol.
    Args:
        index (int): The index of the history file.
        exchange (str): The exchange name (e.g., 'bybit', 'bitstamp').
        symbol (str): The trading symbol (e.g., 'BTCUSD', 'ETHUSD')

    Returns:
        str: The formatted filename.
    """
    return f'./history/{exchange}/{symbol}_M1_{index}.json'


def load_existing_history(exchange, symbol):
    """
    Loads existing history data from files.
    Args:
        exchange (str): The exchange name.
        symbol (str): The trading symbol.

    Returns:
        list: Loaded history data or an empty list if no file found.
    """
    loadedData = []
    directory = f'./history/{exchange}/'

    try:
        # Get a list of all files in the specified directory
        file_list = os.listdir(directory)

        # Define a custom sorting function
        def numericalSort(value):
            parts = re.split(r'(\d+)', value)
            parts[1::2] = map(int, parts[1::2])
            return parts

        # Sort the filenames numerically
        sorted_files = sorted(file_list, key=numericalSort)

        cnt = 0
        for filename in sorted_files:
            if filename.startswith(f'{symbol}_M1_') and filename.endswith('.json'):
                # Load data from each valid history file
                with open(os.path.join(directory, filename), 'r') as file:
                    file_data = json.load(file)
                    if len(file_data)>0:
                        loadedData += file_data
                        cnt +=1

        if not loadedData:
            print(f"No history files found for {exchange} - {symbol}. Starting fresh.")

    except FileNotFoundError:
        print(f"Directory {directory} not found.")

    return [loadedData, cnt]


def is_future_time(start_time, milli):
    """
    Checks if the given time is in the future compared to the current time (minus two latest minutes).

    Args:
        start_time: The time to be checked, in seconds or milliseconds.

    Returns:
        True if the time is in the future, False otherwise.
    """
    if milli:
        time_now = int(datetime.now().timestamp()*1000) - 120000
    else:
        time_now = int(datetime.now().timestamp()) - 120

    return start_time > time_now


def data_to_dataframe(data, exchange):
    """converts price data to pandas dataframe format"""
    df = pd.DataFrame.from_dict(data)
    if exchange in ['bybit', 'bybit-linear']:
        df.columns = ['time', 'open', 'high', 'low', 'close','volume','turnover']
        df['time'] = pd.to_datetime(df['time'].astype('int64'), unit='ms')
        df.set_index('time', inplace=True)
    elif exchange == 'bitstamp':
        df.rename(columns={'timestamp': 'time'}, inplace=True)
        df['time'] = pd.to_datetime(df['time'].astype('int64'), unit='s')
        df.set_index('time', inplace=True)
    elif exchange in ['kucoin-spot', 'kucoin-futures']:
        df.columns = ['time', 'open', 'close', 'high', 'low', 'volume', 'amount']
        df['time'] = pd.to_datetime(df['time'].astype('int64'), unit='s')
        df.set_index('time', inplace=True)
    elif exchange == 'okx':
        df.columns = ['time', 'open', 'high', 'low', 'close', 'volume', 'volCcy','volCcyQuote','confirm']
        df['time'] = pd.to_datetime(df['time'].astype('int64'), unit='ms')
        df.set_index('time', inplace=True)
    elif exchange == 'bitfinex':
        df.columns = ['time', 'open', 'close', 'high', 'low', 'volume']
        df['time'] = pd.to_datetime(df['time'].astype('int64'), unit='ms')
        df.set_index('time', inplace=True)
    else:
        raise ValueError("Exchange not found: {}".format(exchange))
    return df