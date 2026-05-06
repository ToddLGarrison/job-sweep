import notion_api as notion
from models import Company, JobListing


def is_duplicate(company: Company, listing: JobListing) -> bool:
    if listing.url and notion.query_by_url(listing.url):
        return True
    if notion.query_by_name(company.name, listing.title):
        return True
    return False
