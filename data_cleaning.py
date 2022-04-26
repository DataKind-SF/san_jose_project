import pandas as pd

def read_upload(file, filename):
    if filename[-8:] == '.csv.zip':
      df = pd.read_csv(file, compression='zip')
    elif filename[-4:] == '.csv':
      df = pd.read_csv(file)
    else:
      raise('File is not a .csv or .csv.zip file')
    
    return df

def clean_lat_long(df, lat_col, long_col):
    prior_len_df = len(df)
    df = df[df[[long_col, lat_col]].isnull().sum(axis=1) == 0].reset_index(drop = True)
    missing_lat_long_value = prior_len_df - len(df)
    
    df[long_col] = df[long_col].astype(float, errors = 'raise')
    df[lat_col] = df[lat_col].astype(float, errors = 'raise')
    
    non_us_filter = ((df[long_col] > -84) | (df[long_col] < -179) |
                     (df[lat_col] < 17) | (df[lat_col] > 72))
    non_us_lat_long_value = non_us_filter.sum()
    df = df[~non_us_filter].reset_index(drop = True)
    
    return df, missing_lat_long_value, non_us_lat_long_value
    
     
      
    