
import pandas as pd

def apply_confirmation_policy(df, coherence_min, persistence_min):
    """
    Applies the conservative confirmation policy to the dataframe.
    
    Invariant: 
    status == 'CONFIRMED' IMPLIES (coherence_score >= coherence_min AND persistence_score >= persistence_min)
    
    Args:
        df (pd.DataFrame): Input dataframe with 'coherence_score' and 'persistence_score'.
                           If columns missing, assumes 0 (conservative).
        coherence_min (float): Minimum coherence score [0,1].
        persistence_min (float): Minimum persistence score [0,1].
        
    Returns:
        pd.DataFrame: DataFrame with added/updated 'anomaly_status' column.
    """
    if df is None or df.empty:
        return df

    # Ensure scores exist (fill with 0 if missing for safety)
    if 'coherence_score' not in df.columns:
        df['coherence_score'] = 0.0
    if 'persistence_score' not in df.columns:
        df['persistence_score'] = 0.0

    def determine_status(row):
        is_coherent = row['coherence_score'] >= coherence_min
        is_persistent = row['persistence_score'] >= persistence_min
        
        if is_coherent and is_persistent:
            return "CONFIRMED"
        else:
            return "unconfirmed" # Lowercase or 'CANDIDATE' as per preference. Using 'unconfirmed' for now.

    df['anomaly_status'] = df.apply(determine_status, axis=1)
    return df
