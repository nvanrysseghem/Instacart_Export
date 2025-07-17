#!/usr/bin/env python3
import json
import argparse
import re
import csv
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from statistics import mean, median, stdev
from typing import Dict, List, Tuple, Optional
import logging

from rapidfuzz import fuzz, process

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class InstacartAnalyzer:
    """Enhanced analyzer for Instacart order data"""
    
    def __init__(self, orders_file: str):
        self.orders_file = orders_file
        self.orders = []
        self.items = defaultdict(lambda: {
            'quantities': [],
            'prices': [],
            'order_dates': [],
            'total_quantity': 0,
            'order_count': 0
        })
        
    def load_orders(self, after_date: Optional[datetime] = None) -> None:
        """Load and filter orders from JSON file"""
        logger.info(f"Loading orders from {self.orders_file}")
        
        with open(self.orders_file, 'r') as f:
            all_orders = json.load(f)
        
        # Filter orders
        for order in all_orders:
            if order.get("cancelled", False):
                continue
                
            order_date = datetime.strptime(order['dateTime'], '%Y-%m-%d %H:%M')
            
            if after_date and order_date <= after_date:
                continue
                
            self.orders.append(order)
        
        logger.info(f"Loaded {len(self.orders)} valid orders")
    
    def extract_items(self) -> None:
        """Extract and aggregate item information"""
        for order in self.orders:
            order_date = datetime.strptime(order['dateTime'], '%Y-%m-%d %H:%M')
            
            for item in order.get('items', []):
                # Create unique identifier
                item_id = (item['name'], item['unitDescription'])
                
                # Extract quantity (handle various formats)
                quantity = self._parse_quantity(item['quantity'])
                
                # Extract price
                price = self._parse_price(item['unitPrice'])
                
                # Store data
                self.items[item_id]['quantities'].append(quantity)
                self.items[item_id]['prices'].append((order_date, price))
                self.items[item_id]['order_dates'].append(order_date)
                self.items[item_id]['total_quantity'] += quantity
                self.items[item_id]['order_count'] += 1
    
    def _parse_quantity(self, quantity_str: str) -> float:
        """Parse quantity string to float"""
        # Remove non-numeric characters except decimal point
        cleaned = re.sub(r'[^0-9.]', '', quantity_str)
        try:
            return float(cleaned) if cleaned else 1.0
        except ValueError:
            return 1.0
    
    def _parse_price(self, price_str: str) -> float:
        """Parse price string to float"""
        cleaned = re.sub(r'[^0-9.]', '', price_str)
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0
    
    def analyze_item(self, item_id: Tuple[str, str]) -> Dict:
        """Comprehensive analysis of a single item"""
        item_data = self.items[item_id]
        
        if not item_data['order_dates']:
            return {}
        
        # Time-based calculations
        first_order = min(item_data['order_dates'])
        last_order = max(item_data['order_dates'])
        days_span = (last_order - first_order).days or 1
        months_span = days_span / 30.44  # Average days per month
        
        # Quantity statistics
        quantities = item_data['quantities']
        avg_quantity_per_order = mean(quantities) if quantities else 0
        
        # Purchase frequency
        if len(item_data['order_dates']) > 1:
            # Calculate days between purchases
            sorted_dates = sorted(item_data['order_dates'])
            days_between = [(sorted_dates[i+1] - sorted_dates[i]).days 
                           for i in range(len(sorted_dates)-1)]
            avg_days_between = mean(days_between) if days_between else 0
        else:
            avg_days_between = 0
        
        # Price analysis
        prices = [p[1] for p in item_data['prices']]
        price_changes = self._analyze_price_changes(item_data['prices'])
        
        return {
            'name': item_id[0],
            'unit': item_id[1],
            'total_quantity': item_data['total_quantity'],
            'order_count': item_data['order_count'],
            'avg_quantity_per_order': round(avg_quantity_per_order, 2),
            'quantity_per_month': round(item_data['total_quantity'] / months_span, 2) if months_span > 0 else 0,
            'avg_days_between_orders': round(avg_days_between, 1),
            'first_ordered': first_order.strftime('%Y-%m-%d'),
            'last_ordered': last_order.strftime('%Y-%m-%d'),
            'current_price': prices[-1] if prices else 0,
            'avg_price': round(mean(prices), 2) if prices else 0,
            'min_price': min(prices) if prices else 0,
            'max_price': max(prices) if prices else 0,
            'price_volatility': round(stdev(prices), 2) if len(prices) > 1 else 0,
            'price_changes': price_changes
        }
    
    def _analyze_price_changes(self, price_history: List[Tuple[datetime, float]]) -> List[Dict]:
        """Analyze price changes over time"""
        if len(price_history) < 2:
            return []
        
        changes = []
        for i in range(1, len(price_history)):
            if price_history[i][1] != price_history[i-1][1]:
                change_amount = price_history[i][1] - price_history[i-1][1]
                change_percent = (change_amount / price_history[i-1][1] * 100) if price_history[i-1][1] > 0 else 0
                
                changes.append({
                    'date': price_history[i][0].strftime('%Y-%m-%d'),
                    'old_price': price_history[i-1][1],
                    'new_price': price_history[i][1],
                    'change_amount': round(change_amount, 2),
                    'change_percent': round(change_percent, 1)
                })
        
        return changes
    
    def group_similar_items(self, similarity_threshold: int = 80) -> List[List[Tuple[str, str]]]:
        """Group similar items using fuzzy matching"""
        items_list = list(self.items.keys())
        groups = []
        used = set()
        
        for i, item1 in enumerate(items_list):
            if item1 in used:
                continue
                
            group = [item1]
            used.add(item1)
            
            # Find similar items
            item1_name = item1[0].lower()
            
            for j, item2 in enumerate(items_list[i+1:], i+1):
                if item2 in used:
                    continue
                    
                item2_name = item2[0].lower()
                
                # Check similarity
                similarity = fuzz.token_sort_ratio(item1_name, item2_name)
                if similarity >= similarity_threshold:
                    group.append(item2)
                    used.add(item2)
            
            if len(group) > 1:
                groups.append(group)
        
        return groups
    
    def generate_insights(self) -> Dict:
        """Generate shopping insights and patterns"""
        insights = {
            'total_orders': len(self.orders),
            'date_range': {
                'first': min(o['dateTime'] for o in self.orders),
                'last': max(o['dateTime'] for o in self.orders)
            },
            'total_spent': sum(float(re.sub(r'[^0-9.]', '', o['total'])) for o in self.orders),
            'avg_order_value': 0,
            'most_frequent_items': [],
            'highest_spending_items': [],
            'shopping_patterns': {},
            'price_alerts': []
        }
        
        # Average order value
        insights['avg_order_value'] = round(insights['total_spent'] / insights['total_orders'], 2)
        
        # Most frequent items (top 10)
        frequent_items = sorted(self.items.items(), 
                               key=lambda x: x[1]['order_count'], 
                               reverse=True)[:10]
        insights['most_frequent_items'] = [
            {
                'name': item[0][0],
                'unit': item[0][1],
                'order_count': item[1]['order_count'],
                'percentage': round(item[1]['order_count'] / insights['total_orders'] * 100, 1)
            }
            for item in frequent_items
        ]
        
        # Highest spending items
        item_spending = []
        for item_id, data in self.items.items():
            total_spent = sum(data['quantities'][i] * data['prices'][i][1] 
                            for i in range(len(data['quantities'])))
            item_spending.append((item_id, total_spent))
        
        top_spending = sorted(item_spending, key=lambda x: x[1], reverse=True)[:10]
        insights['highest_spending_items'] = [
            {
                'name': item[0][0],
                'unit': item[0][1],
                'total_spent': round(item[1], 2)
            }
            for item in top_spending
        ]
        
        # Shopping patterns by day of week
        day_counts = Counter()
        for order in self.orders:
            order_date = datetime.strptime(order['dateTime'], '%Y-%m-%d %H:%M')
            day_counts[order_date.strftime('%A')] += 1
        
        insights['shopping_patterns']['by_day'] = dict(day_counts)
        
        # Price increase alerts
        for item_id, data in self.items.items():
            if len(data['prices']) >= 2:
                recent_price = data['prices'][-1][1]
                avg_price = mean([p[1] for p in data['prices'][:-1]])
                
                if recent_price > avg_price * 1.2:  # 20% increase
                    insights['price_alerts'].append({
                        'name': item_id[0],
                        'unit': item_id[1],
                        'current_price': recent_price,
                        'avg_price': round(avg_price, 2),
                        'increase_percent': round((recent_price - avg_price) / avg_price * 100, 1)
                    })
        
        return insights
    
    def export_report(self, output_file: str, format: str = 'csv') -> None:
        """Export analysis report in various formats"""
        logger.info(f"Generating {format} report: {output_file}")
        
        # Analyze all items
        results = []
        for item_id in self.items:
            analysis = self.analyze_item(item_id)
            if analysis:
                results.append(analysis)
        
        # Sort by quantity per month
        results.sort(key=lambda x: x['quantity_per_month'], reverse=True)
        
        if format == 'csv':
            self._export_csv(results, output_file)
        elif format == 'json':
            self._export_json(results, output_file)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _export_csv(self, results: List[Dict], output_file: str) -> None:
        """Export results to CSV"""
        if not results:
            logger.warning("No results to export")
            return
        
        # Define CSV columns
        fieldnames = [
            'name', 'unit', 'total_quantity', 'order_count',
            'avg_quantity_per_order', 'quantity_per_month',
            'avg_days_between_orders', 'first_ordered', 'last_ordered',
            'current_price', 'avg_price', 'min_price', 'max_price',
            'price_volatility', 'price_changes_summary'
        ]
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for result in results:
                # Format price changes for CSV
                price_changes = result.get('price_changes', [])
                if price_changes:
                    changes_summary = '; '.join([
                        f"{c['date']}: ${c['old_price']:.2f} → ${c['new_price']:.2f} ({c['change_percent']:+.1f}%)"
                        for c in price_changes[-3:]  # Last 3 changes
                    ])
                else:
                    changes_summary = "No changes"
                
                row = {k: result.get(k, '') for k in fieldnames[:-1]}
                row['price_changes_summary'] = changes_summary
                
                writer.writerow(row)
    
    def _export_json(self, results: List[Dict], output_file: str) -> None:
        """Export results to JSON"""
        output = {
            'analysis_date': datetime.now().isoformat(),
            'orders_analyzed': len(self.orders),
            'unique_items': len(results),
            'insights': self.generate_insights(),
            'items': results
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, default=str)

def main():
    parser = argparse.ArgumentParser(description='Analyze Instacart order data')
    parser.add_argument('file_path', help='Input JSON file path')
    parser.add_argument('--after', help='Filter orders after date (Y-m-d H:M)')
    parser.add_argument('--format', choices=['csv', 'json'], default='csv',
                       help='Output format (default: csv)')
    parser.add_argument('--output', help='Output file path (default: input_file.analysis.ext)')
    parser.add_argument('--insights', action='store_true',
                       help='Print shopping insights to console')
    
    args = parser.parse_args()
    
    # Initialize analyzer
    analyzer = InstacartAnalyzer(args.file_path)
    
    # Parse after date if provided
    after_date = None
    if args.after:
        after_date = datetime.strptime(args.after, '%Y-%m-%d %H:%M')
    
    # Load and analyze data
    analyzer.load_orders(after_date)
    analyzer.extract_items()
    
    # Generate output filename if not provided
    if args.output:
        output_file = args.output
    else:
        base_name = args.file_path.rsplit('.', 1)[0]
        output_file = f"{base_name}.analysis.{args.format}"
    
    # Export report
    analyzer.export_report(output_file, args.format)
    
    # Print insights if requested
    if args.insights:
        insights = analyzer.generate_insights()
        print("\n=== Shopping Insights ===")
        print(f"Total orders: {insights['total_orders']}")
        print(f"Date range: {insights['date_range']['first']} to {insights['date_range']['last']}")
        print(f"Total spent: ${insights['total_spent']:.2f}")
        print(f"Average order value: ${insights['avg_order_value']:.2f}")
        
        print("\n--- Most Frequent Items ---")
        for item in insights['most_frequent_items'][:5]:
            print(f"  {item['name']} ({item['unit']}): {item['order_count']} orders ({item['percentage']}%)")
        
        if insights['price_alerts']:
            print("\n--- Price Alerts ---")
            for alert in insights['price_alerts'][:5]:
                print(f"  {alert['name']}: ${alert['current_price']:.2f} "
                      f"(+{alert['increase_percent']}% from avg ${alert['avg_price']:.2f})")
    
    logger.info(f"Analysis complete. Report saved to: {output_file}")

if __name__ == "__main__":
    main()
