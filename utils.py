import gc
import os
import pandas as pd
from statsmodels.stats.proportion import proportions_ztest
from statsmodels.stats.multitest import multipletests
import plotly.graph_objs as go
from fpdf import FPDF

SLOW_RESPONSE_THRESHOLD_SECONDS = 720


def add_plot_to_pdf(pdf, reference_gdf, geojson, col_name, title, colorscale='hot_r'):
    plot_df = reference_gdf.groupby(['zcta'])[col_name].mean().round().reset_index()
    
    fig = go.Figure(go.Choroplethmapbox(z=plot_df[col_name],
                                        locations=plot_df['zcta'], 
                                        colorscale=colorscale,
                                        colorbar=dict(thickness=20, ticklen=3),
                                        geojson=geojson,
                                        text=plot_df['zcta'],
                                        hovertemplate='<b>Zip code</b>: <b>%{text}</b>'+
                                                      '<br><b>' + col_name + '</b>: %{z}<br>',
                                        marker_line_width=0.1, marker_opacity=0.7))

    fig.update_layout(title_text=title, title_x =0.5, width=750, height=700,
                      mapbox=dict(style='open-street-map',
                                  zoom=9.7, 
                                  center = {"lat": pd.Series([point.y for point in reference_gdf.geometry]).mean() ,
                                            "lon":pd.Series([point.x for point in reference_gdf.geometry]).mean()},
                                  ))
    fig.write_image(col_name+'tmp.jpeg') 
    
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.image(col_name+'tmp.jpeg', x=None, y=None, w=150, type='jpeg')
    
    os.remove(col_name+'tmp.jpeg')
    del fig, plot_df, reference_gdf, geojson, col_name, title, colorscale
    gc.collect()
    
    return pdf
    
def test_equity(df, col, threshold, alternative):
  p_val = proportions_ztest([((df[col] <= threshold) & (df['response_time'] > SLOW_RESPONSE_THRESHOLD_SECONDS)).sum(),
                             ((df[col] > threshold) & (df['response_time'] > SLOW_RESPONSE_THRESHOLD_SECONDS)).sum()],
                             [(df[col] <= threshold).sum(), (df[col] > threshold).sum()], alternative=alternative)[1]

  return p_val

def generate_pdf(reference_gdf, geojson, income_median, black_median, hispanic_median):
    pdf = FPDF()
                   
    pdf = add_plot_to_pdf(pdf, reference_gdf, geojson, 'response_time',
                          'Response times by zip code', 'hot_r')
    pdf = add_plot_to_pdf(pdf, reference_gdf, geojson, 'Per Capita Income', 
                          'Average per capita income by zip code', 'algae')
    
    # These plots are commented out to save memory on the free Heroku instance
    # pdf = add_plot_to_pdf(pdf, reference_gdf, geojson, 'Black', 
    #                       'Percentage of population who are Black by zip code', 'purp')
    # pdf = add_plot_to_pdf(pdf, reference_gdf, geojson, 'Hispanic/Latino Ethnicity', 
    #                       'Percentage of population who are Hispanic by zip code', 'purp')

    # Add quantitative measures of fairness
    corr_df = reference_gdf.groupby(['zcta'])[['response_time', 'Per Capita Income', 
                                               'Black', 'Hispanic/Latino Ethnicity']].mean().corr().iloc[0, 1:]  
    
    # These tests have been commented out to save memory on the free Heroku instance
    # income_pval = test_equity(reference_gdf, 'Per Capita Income', income_median, 'larger')
    # black_pval = test_equity(reference_gdf, 'Black', black_median, 'smaller')
    # hispanic_pval = test_equity(reference_gdf, 'Hispanic/Latino Ethnicity', hispanic_median, 'smaller')
    # adjusted_pvals = multipletests([income_pval, black_pval, hispanic_pval], method='holm')[1]
    
    pdf.set_font('Arial', 'B', 12)
    pdf.add_page()
    pdf.multi_cell(txt="Positive correlations mean response time was slower for zip codes with more residents of color"\
                       " or with lower income (considered strong above 0.7)"\
                       "\nCorrelation with lower-income residents: " + str(corr_df[0].round(2)) +\
                       "\nCorrelation with Black residents: " + str(corr_df[1].round(2)) +\
                       "\nCorrelation with Hispanic residents: " + str(corr_df[2].round(2)), w=175, h=25, align='L')
                       # "P-values below .05 cause us to reject the null hypothesis of equal proportion of responses"\
                       # " by zip code demographic within 12 minutes" +\
                       # "\nP-value for lower-income residents: " + str(adjusted_pvals[0].round(2)) +\
                       # "\nP-value for Black residents: " + str(adjusted_pvals[1].round(2)) +\
                       # "\nP-value for Hispanic residents: " + str(adjusted_pvals[2].round(2)), w=175, h=25, align='L')
    
    del reference_gdf, geojson, corr_df #, income_pval, black_pval, hispanic_pval, adjusted_pvals
    gc.collect()
    
    return pdf
