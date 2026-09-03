#!/bin/bash
#
# Example configuration file for DB2 Audit Loader
# Copy this file and customize with your actual credentials
#
# Usage:
#   1. Copy: cp example_config.sh my_config.sh
#   2. Edit my_config.sh with your credentials
#   3. Source: source my_config.sh
#   4. Run: python load_audit_files.py --connection $CONNECTION_TYPE ...
#

# ============================================================================
# CONNECTION SETTINGS
# ============================================================================

# Connection type: "local" or "jdbc"
export CONNECTION_TYPE="local"

# Database settings
export DB_NAME="<your-database>"
export DB_SCHEMA="<your-schema>"

# ============================================================================
# JDBC SETTINGS (only needed if CONNECTION_TYPE="jdbc")
# ============================================================================

# JDBC connection URL
# Format (standard): jdbc:db2://hostname:port/database
# Format (SSL/Cloud): jdbc:db2://hostname:port/database:sslConnection=true;
export JDBC_URL="jdbc:db2://<hostname>:<port>/<database>:sslConnection=true;"

# JDBC credentials
export JDBC_USER="<your-jdbc-user>"
export JDBC_PASSWORD="<your-jdbc-password>"

# JDBC driver (usually no need to change)
export JDBC_DRIVER="com.ibm.db2.jcc.DB2Driver"

# Path to DB2 JDBC driver JAR file
export DB2_JDBC_JAR="/path/to/db2jcc4.jar"
export CLASSPATH="${DB2_JDBC_JAR}:${CLASSPATH}"

# ============================================================================
# IBM CLOUD OBJECT STORAGE (COS) SETTINGS
# ============================================================================

# COS bucket name
export COS_BUCKET="<your-bucket>"

# COS endpoint URL
# Find your endpoint at: https://cloud.ibm.com/docs/cloud-object-storage?topic=cloud-object-storage-endpoints
export COS_ENDPOINT="<your-cos-endpoint>"

# COS credentials (HMAC)
# Get from IBM Cloud Console > Object Storage > Service Credentials
export COS_ACCESS_KEY="<your-access-key-id>"
export COS_SECRET_KEY="<your-secret-access-key>"

# COS region (optional)
export COS_REGION="<your-region>"

# S3 prefix/folder path (optional)
export S3_PREFIX=""

# ============================================================================
# LOAD SETTINGS
# ============================================================================

# Load type: "insert" (append) or "replace" (truncate first)
export LOAD_TYPE="insert"

# Local directory for downloaded files
export LOCAL_DIR="del_files"

# ============================================================================
# EXAMPLE COMMANDS
# ============================================================================

# After sourcing this file, you can run:

# Full load (download + load + validate)
# python load_audit_files.py \
#   --connection $CONNECTION_TYPE \
#   --database $DB_NAME \
#   --schema $DB_SCHEMA \
#   --jdbc-url "$JDBC_URL" \
#   --jdbc-user "$JDBC_USER" \
#   --jdbc-password "$JDBC_PASSWORD" \
#   --jdbc-jar "$DB2_JDBC_JAR" \
#   --bucket $COS_BUCKET \
#   --cos-endpoint $COS_ENDPOINT \
#   --cos-access-key $COS_ACCESS_KEY \
#   --cos-secret-key $COS_SECRET_KEY \
#   --load-type $LOAD_TYPE \
#   --files db2audit.db.BLUDB.log.0.20260827221347524319.context.del

# Validation of database records by time range
# python validate_audit_data.py \
#   --connection $CONNECTION_TYPE \
#   --database $DB_NAME \
#   --schema $DB_SCHEMA \
#   --jdbc-url "$JDBC_URL" \
#   --jdbc-user "$JDBC_USER" \
#   --jdbc-password "$JDBC_PASSWORD" \
#   --jdbc-jar "$DB2_JDBC_JAR" \
#   --start-time "<YYYY-MM-DD HH:MM:SS>" \
#   --end-time "<YYYY-MM-DD HH:MM:SS>" \
#   --detailed \
#   --export-csv validation_results.csv

echo "✅ Configuration loaded successfully"
echo "   Connection Type: $CONNECTION_TYPE"
echo "   Database: $DB_NAME"
echo "   Schema: $DB_SCHEMA"
echo "   COS Bucket: $COS_BUCKET"
echo "   Time Range: $START_TIME to $END_TIME"

