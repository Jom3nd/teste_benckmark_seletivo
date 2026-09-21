from src.order.service import OrderService
def test_update_delete():
 s=OrderService(); s.create(1,"A"); assert s.update(1,"B").name=="B"; assert s.delete(1).id==1
def test_list_find():
 s=OrderService(); s.create(2,"B"); s.create(1,"A"); assert [x.id for x in s.list_all()]==[1,2]; assert s.find_by_name("B").id==2
