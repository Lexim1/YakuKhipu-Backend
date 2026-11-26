"""Dobles de persistencia para pruebas HTTP; no crea ni conecta ninguna BD.

Evalúa expresiones ORM básicas de permisos y estado. No prueba SQL ni transacciones PostgreSQL.
"""
from collections import defaultdict
from types import SimpleNamespace
from sqlalchemy.sql.elements import BinaryExpression,BooleanClauseList,BindParameter,TextClause,Null,True_,False_
from sqlalchemy.sql import operators


class Result(list):
    def all(self): return list(self)
    def first(self): return self[0] if self else None
    def mappings(self): return self
    def scalar(self): return self.first()


class Memoria:
    def __init__(self):
        self.tablas=defaultdict(dict)
        self.commits=0
        self.rollbacks=0

    def add(self,obj):
        table=type(obj).__tablename__
        if getattr(obj,'id',None) is None: obj.id=len(self.tablas[table])+1
        self.tablas[table][obj.id]=obj

    def get(self,model,key,**_opciones): return self.tablas[model.__tablename__].get(key)
    def flush(self): pass
    def refresh(self,obj): pass
    def commit(self): self.commits+=1
    def rollback(self): self.rollbacks+=1
    def close(self): pass
    def merge(self,obj):
        if not getattr(obj,'id',None): obj.id=obj.clave
        self.add(obj)

    def _value(self,expr,row):
        if isinstance(expr,BindParameter): return expr.value
        if isinstance(expr,Null): return None
        if isinstance(expr,True_): return True
        if isinstance(expr,False_): return False
        table=getattr(getattr(expr,'table',None),'name',None)
        if table and table!=type(row).__tablename__:
            key=getattr(row,{'tramite':'tramite_id','documento':'documento_id'}.get(table,''),None)
            row=self.tablas[table].get(key)
        return getattr(row,expr.key,None)

    def _matches(self,expr,row):
        if isinstance(expr,TextClause): return True  # presencia fuente: cubierta en prueba PostgreSQL
        if isinstance(expr,BooleanClauseList): return all(self._matches(c,row) for c in expr.clauses)
        if isinstance(expr,BinaryExpression):
            left,right=self._value(expr.left,row),self._value(expr.right,row)
            ops={operators.eq:lambda:left==right,operators.ne:lambda:left!=right,
                 operators.is_:lambda:left is right,operators.is_not:lambda:left is not right,
                 operators.in_op:lambda:left in right,operators.not_in_op:lambda:left not in right}
            return ops[expr.operator]()
        raise AssertionError(f'Expresión no soportada por el doble: {expr}')

    def scalars(self,query):
        desc=query.column_descriptions[0]
        model=desc['entity']
        rows=[r for r in self.tablas[model.__tablename__].values() if all(self._matches(e,r) for e in query._where_criteria)]
        for order in reversed(query._order_by_clauses):
            base=getattr(order,'element',order)
            rows.sort(key=lambda r:(self._value(base,r) is None,self._value(base,r)),reverse=getattr(order,'modifier',None)==operators.desc_op)
        if query._limit_clause is not None: rows=rows[:query._limit_clause.value]
        if desc['expr'] is not model: rows=[self._value(desc['expr'],r) for r in rows]
        return Result(rows)

    def execute(self,query,params=None):
        if isinstance(query,TextClause):
            sql=str(query)
            if sql.startswith('SELECT presente'): return Result([True])
            if sql.startswith('SELECT * FROM plazo') or 'FROM procedimiento_fuente' in sql: return Result()
            if sql.startswith('INSERT INTO'): return Result()
            raise AssertionError(f'SQL no sustituido en esta prueba: {sql[:100]}')
        if hasattr(query,'column_descriptions'):
            model=query.column_descriptions[0]['entity']
            rows=[r for r in self.tablas[model.__tablename__].values() if all(self._matches(e,r) for e in query._where_criteria)]
            return Result([tuple(self._value(c,r) for c in query.selected_columns) for r in rows])
        # limpieza de caché (DELETE), sin datos fuente
        return Result()
