from guppy import hpy
import gc
from flask import Flask, request, make_response, render_template
from werkzeug.utils import secure_filename

import pandas as pd
import json
import geopandas as gpd
from geopandas.tools import sjoin

from data_cleaning import read_upload, clean_lat_long
from utils import generate_pdf

app = Flask(__name__, template_folder='templates')
app.secret_key = "super secret key"

LOWER_TIME_BOUND_SECONDS = 60
UPPER_TIME_BOUND_SECONDS = 3600
    
# 2010 Census ZCTA boundaries from https://earthworks.stanford.edu/catalog/stanford-dc841dq9031
zctas_df = gpd.read_file('data/dc841dq9031.shp').to_crs(epsg=4326)
zctas_df_bounds = zctas_df.bounds
# Demographic data from tack-data.com, cross-referenced for confirmation with
# https://github.com/edjzhang/zipbiaschecker where available
demographic_df = pd.read_csv('zip_data.csv')
demographic_df['Zip'] = [str(x).zfill(5) for x in demographic_df['Zip']]

@app.route('/')
def upload_file():
   return render_template('upload.html')

@app.route('/uploader', methods=['GET', 'POST'])
def return_file():
    file = request.files['response_file']
    filename = secure_filename(file.filename)
    
    df = read_upload(file, filename)
      
    print(df.shape)
    
    lat_col = request.form['lat_col']
    long_col = request.form['long_col']
    start_time_col = request.form['start_time_col']
    end_time_col = request.form['end_time_col']
    
    df, missing_lat_long_value, non_us_lat_long_value = clean_lat_long(df, lat_col, long_col)
    print(missing_lat_long_value, 'rows missing latitude and/or longitude')
    print(non_us_lat_long_value, 'rows with latitude and/or longitude outside of the US')
    
    
    zctas_df_subset = zctas_df[(((zctas_df_bounds.miny >= df[lat_col].min()) &\
                                (zctas_df_bounds.miny <= df[lat_col].max())) |\
                                ((zctas_df_bounds.maxy >= df[lat_col].min()) &\
                                (zctas_df_bounds.maxy <= df[lat_col].max()))) &\
                               (((zctas_df_bounds.minx >= df[long_col].min()) &\
                                (zctas_df_bounds.minx <= df[long_col].max())) |\
                                ((zctas_df_bounds.maxx >= df[long_col].min()) &\
                                (zctas_df_bounds.maxx <= df[long_col].max())))]
    print(zctas_df_subset.shape)
    
    # Sample 100 only for the free Heroku deployment; if running locally, can remove this
    df_sample = df.sample(100)
    
    # Join incidents to zip codes
    gdf = gpd.GeoDataFrame(df_sample, geometry=gpd.points_from_xy(df_sample[long_col], 
                                                                  df_sample[lat_col]))
    gdf.crs = zctas_df_subset.crs
    og_len = len(gdf)
    gdf = sjoin(gdf, zctas_df_subset, how="inner")
    new_len = len(gdf)
    no_zip_match = og_len - new_len - non_us_lat_long_value
    print('Number of rows with reasonable lat-longs dropped due to no match:', no_zip_match)
    
    # Join incidents to additional Census data
    gdf = pd.merge(gdf, demographic_df, how='left', left_on='zcta', right_on='Zip')
    print(gdf['Zip'].isnull().sum(), 'rows un-successfully matched with demographic data')
    
    # Calculate response time
    gdf['response_time'] = [x.seconds for x in pd.to_datetime(gdf[end_time_col]) -\
                            pd.to_datetime(gdf[start_time_col])]
    print((gdf[end_time_col].isnull() & ~gdf[start_time_col].isnull()).sum(), 
            'incidents are missing timestamp data due to no {} timestamp'.format(end_time_col))
    print((~gdf[end_time_col].isnull() & gdf[start_time_col].isnull()).sum(), 
            'incidents are missing timestamp data due to no {} timestamp'.format(start_time_col))
    print((gdf[end_time_col].isnull() & gdf[start_time_col].isnull()).sum(), 
            'incidents are missing timestamp data due to no {} or {} timestamps'.format(end_time_col, start_time_col))
    
    missing_timestamps = gdf['response_time'].isnull().sum()
    filtered_df_shape = len(gdf)
    gdf = gdf[~gdf['response_time'].isnull()].reset_index(drop = True)
    
    # Filter and flag unexpected response times
    filtered_df_shape2 = len(gdf)
    print((gdf['response_time'] < LOWER_TIME_BOUND_SECONDS).sum(), 'rows dropped due to response time shorter than a minute')
    print((gdf['response_time'] > UPPER_TIME_BOUND_SECONDS).sum(), 'rows dropped due to response time longer than an hour')
    response_time_out_of_range = ((gdf['response_time'] < LOWER_TIME_BOUND_SECONDS) | (gdf['response_time'] > UPPER_TIME_BOUND_SECONDS)).sum()
    gdf = gdf[(gdf['response_time'] >= LOWER_TIME_BOUND_SECONDS) & (gdf['response_time'] <= UPPER_TIME_BOUND_SECONDS)].reset_index()
    
    income_median = gdf['Per Capita Income'].median()
    black_median = gdf['Black'].median()
    hispanic_median = gdf['Hispanic/Latino Ethnicity'].median()
    print("Median zip-code-average income:", income_median)
    print("Median zip-code-level Black population proportion:", black_median)
    print("Median zip-code-average Hispanic population proportion:", hispanic_median)
        
    zctas_df_subset = zctas_df_subset.to_crs(epsg=4326)
    zctas_df_subset.to_file("data/zctas_df_subset_tmp.geojson", driver = "GeoJSON")
    with open("data/zctas_df_subset_tmp.geojson") as geofile:
      zctas_df_geojson = json.load(geofile)
    
    for k in range(len(zctas_df_geojson['features'])):
      zctas_df_geojson['features'][k]['id'] = \
          zctas_df_geojson['features'][k]['properties']['zcta']
    
    pdf = generate_pdf(gdf, zctas_df_geojson, income_median, black_median, hispanic_median)
    
    response = make_response(pdf.output(dest='S').encode('latin-1'))
    response.headers.set('Content-Disposition', 'attachment', 
                         filename=filename + '_analysis.pdf')
    response.headers.set('Content-Type', 'application/pdf')
    
    del file, filename, df, lat_col, long_col, start_time_col, end_time_col,\
        missing_lat_long_value, non_us_lat_long_value, zctas_df_subset, df_sample,\
        gdf, og_len, new_len, no_zip_match, missing_timestamps, filtered_df_shape,\
        filtered_df_shape2, response_time_out_of_range, income_median, black_median,\
        hispanic_median, zctas_df_geojson, pdf
        
    gc.collect()
    print(hpy().heap())
    
    return response

if __name__ == "__main__":
    app.run(debug=False, port=60000)